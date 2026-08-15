# ARCHITECTURE — the system as it IS

**Status: slice 0 is built and does not yet clear its gate.**
Retrieval runs end to end. `retrieval_at_1` is 0.45 against a floor of 0.70.

This file is deliberately not a design document. `.claude/DESIGN.md` holds what
we intend and why; `.claude/PLAN.md` holds the order. **This file holds only what
exists and runs.** When the two disagree, this one is right and the others are
out of date.

The rule that keeps it honest: **if a PR changes the shape of the system, it
updates this file in the same commit.** A shape change means a new component, a
new boundary between components, a new external dependency, or a change to how
data crosses one of those boundaries. Renaming a function is not a shape change.

## What exists today

```
budgets.toml                 enforced complexity limits
scripts/check_budgets.py     counts things — exits 1 on violation
scripts/check_invariants.py  checks mistakes were not made; --base catches a
                             weakened budget
scripts/fetch_metadata.py    caches ACS metadata to data/raw/ (no key)
scripts/verify_golden.py     every expect_table checked against that metadata
scripts/build_index.py       builds index_store/ (needs OPENAI_API_KEY)
scripts/eval_retrieval.py    the scoreboard; --rerank, --holdout
scripts/score_synthetic.py   generated-question quality, on a 600 sample
evals/golden_questions.toml  66 scorable: 4 core, 40 long-tail, 14 trap,
                             8 held out. All verified 2026-08-14.
evidence/latest.json         last measured run
evidence/retrieval_steps.md  every step's number, and what the plan got wrong
docs/playbooks/review-pr.md  canonical review procedure
pyproject.toml               uv workspace root; ruff + mypy + pytest config
api/pyproject.toml           the app's dependencies (3 so far)
.github/workflows/check.yml  the gate, on every PR
.github/workflows/build-index.yml  manual; publishes the index release asset
```

### Retrieval — `api/src/retrieval/`, 8 modules

```
metadata.py      fetch + cache ACS groups/variables/geography; family_id(),
                 is_subject_table()
availability.py  (dataset, vintage, table) -> universe + variable list.
                 Built for slice 3's guards; slice 0 uses its table union.
text.py          vintage-token stripping, !!-label unpacking, tokenizing
bm25.py          Okapi BM25, no dependency; corpus-derived stopwords
embedding.py     OpenAI embeddings; imports the client INSIDE the functions
synthetic.py     LLM question generation, cached and committed
build.py         assembles the artifact. Reaches OpenAI.
index.py         loads the artifact, search(question, k). Never builds.
rerank.py        LLM picks one of the top k. NOT called by search().
```

The boundary that matters: **`build.py` reaches OpenAI, `index.py` does not.**
The artifact is produced offline and, in production, downloaded into the image.
Nothing builds an index at import or at request time.

`index.py` caches the loaded index at module scope — the one piece of
module-level state this project allows, sanctioned because it is read-only.

### Data and artifacts

```
data/raw/                     14 MB cached ACS metadata. Gitignored.
                              ACS5 2016-2024, ACS1 2016-2024 (no 2020).
data/synthetic_questions.json 8,748 questions, 1 MB, COMMITTED and readable.
                              Currently not fed to the index — see below.
index_store/lexical.json.gz   756 table families: ids, titles, universes,
                              members, BM25 postings. Gitignored.
index_store/semantic.npz       756 x 3072 float32 embeddings.
index_store/availability.json.gz  the vintage matrix.
```

### What the index contains, and what it dropped

1,458 tables in the union across all vintages → **756 documents**:

- **588** race iterations (`B19013A`) and Puerto Rico variants folded into their
  base table. They are the same table filtered, they carry near-identical
  titles, and they crowded out their own parents. Members are retained in the
  artifact and become slice 1's `alternatives[]`.
- **114** `B00`/`B98`/`B99` survey-quality tables dropped — allocation rates and
  sample counts, never the subject of a question.

`search()` ranks on embeddings alone. BM25 is built and unused: equal-weight RRF
measured *worse* than embeddings alone on every metric. It is kept for the query
that names a table ID verbatim, which the eval set does not test.

`check_budgets.py` exits 1 on `retrieval_at_1: 0.45 (limit 0.7)` and
`synthetic_self_retrieval: 0.34 (limit 0.95)`. Both are honest failures;
`evidence/retrieval_steps.md` has the full ladder and the diagnosis.

## What each slice adds here

Fill these in as they ship. Delete this list when it is no longer a list of
futures.

| slice | adds to this file |
|---|---|
| ~~0~~ | ~~the index~~ — done, above |
| 1 | the agent loop, the five tools, the response contract, `POST /ask` |
| 2 | `web/`, the generated client, the CI staleness check |
| 3 | fan-out over years and geographies; the guard evaluation point |
| 4 | the canvas and its state model |
| *spike* | *nothing — it produces a decision in DESIGN §9, not code* |
| 5 | Postgres, `thread_id`, conversation persistence |
| 6 | follow-up reference resolution |
| 7 | the report worker and object storage |
| 8 | auth, deployment topology, the container and what is baked into it |

## Diagram

None yet. When there is one, it goes here and it shows what runs — not what was
planned.
