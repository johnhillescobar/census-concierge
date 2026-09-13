# Process evidence

Audit-time evidence for `docs/playbooks/run-slice.md`. The adversarial matrix, the
defect index and the pinned transcripts live here so the playbook stays short
enough to hold in context on every turn. Read this file when checking whether a
rule still earns its place - not mid-implementation.

Not counted against `doc_lines`: this is evidence, not instruction. Same carve-out
as `evidence/retrieval_steps.md`.

`api/tests/test_process.py` re-runs the pinned transcripts below and checks that
every citation in the adversarial matrix resolves to a section in the defect
index. A pinned transcript that stops reproducing is the failure that check exists
to catch: the whole argument of the playbook is that only real output counts.

The matrix and the index start short on purpose. Slice 0 shipped without a
pull-request defect history; every row below is a measured finding from
building that index. A row is added when a real defect is caught, never to
look thorough.

---

## Adversarial matrix

Each row names a probe, and the slice or PR whose defect it would have caught. A
row that cannot name one does not belong here - that is what stops the matrix
decaying into virtuous-sounding lines nobody reads.

| Probe | Caught in |
| --- | --- |
| **Identical inputs ranked by float noise** - two documents that embed to byte-identical text | slice-0: 120 `B`/`C` twins embedded identically; `text-embedding-3-large` returns different vectors per batch position (1.3e-3), so `C15003` outranked `B15003` on rebuild noise alone |
| **A family returned by one member** - a table published only as `A`-`I` iterations coming back as the general table | slice-0: `B28009`, published only as `B28009A-I`, put "Population in households who are White alone" at rank 1 for a broadband question |
| **A ranking change measured on the tuning set alone**, at n=40 where the standard error is ~7 points | slice-0: equal-weight RRF fusion scored *below* embeddings on every metric (@1 0.40 -> 0.28); kept built, unused by `search()` |
| **"Expect the largest jump" checked against the number**, not the intuition | slice-0: synthetic questions were the largest *drop* (@1 0.40 -> 0.25); generation is kept and committed, the embedding no longer reads it |

---

## Pinned transcripts

Re-run in-process by `api/tests/test_process.py` (no shell: `cmd.exe` has no
`grep`). Each pins a fact about the slice-0 corrections to a commit that will not
move.

```
$ git show 56aae62:api/src/retrieval/build.py | grep -n "def _fold_identical_twins"
58:def _fold_identical_twins(
```

```
$ git show 56aae62:api/src/retrieval/embedding.py | grep -n "not bit-deterministic across batch positions"
23:# The API is not bit-deterministic across batch positions: the same string
```

---

## Defect index

Every citation in the matrix resolves to a heading here.

### slice-0

The index-quality findings from `evidence/retrieval_steps.md`, recorded here as
the defects a Gate 1 probe would target.

- **Identical `B`/`C` twins ranked by float noise.** 120 of 756 documents embedded
  to byte-identical text because a `C` table is its `B` with categories collapsed
  and the same title, universe and concept. Of 600 synthetic questions the 97
  asking for such a `C` scored 0% at rank 1 - not hard to rank, impossible. The
  winner was unstable: `text-embedding-3-large` is not bit-deterministic across
  batch positions, so `C15003` sat above `B15003` for "educational attainment in
  Cook County" and could flip on any rebuild. Fixed in `56aae62` by folding each
  `C` into the `B` it is textually identical to, keeping the `C` reachable through
  `members`. *Backs the "identical inputs ranked by float noise" row.*
- **A race iteration returned as the general table.** `B28009` is published only as
  `B28009A-I`; representing the family by its first member ranked "Population in
  households who are White alone" first for a broadband question. A race iteration
  returned as the general table is the exact silent wrong answer this product
  exists to prevent. 14 iteration-only families dropped. *Backs the "family
  returned by one member" row.*
- **RRF fusion measured worse, not better.** The slice-0 plan prescribed BM25 +
  embedding fusion. Equal-weight RRF scored below embeddings alone on every metric
  (@1 0.40 -> 0.28, @5 0.80 -> 0.68). BM25 at @1 0.18 is not strong enough to earn
  an equal vote, and any weight is fitted to 40 questions. BM25 stays built and is
  what answers a query naming a table ID verbatim, which the eval set never does.
  *Backs the "ranking change measured on the tuning set alone" row.*
- **Synthetic questions measured worse, not better.** The plan expected "the
  largest jump" here; it was the largest drop (@1 0.40 -> 0.25, MRR 0.55 -> 0.47).
  Six generic ways of asking about a table describe its topic while blurring what
  separates it from its neighbours, and neighbours are the whole problem.
  Generation is kept and committed; the embedding no longer reads it. *Backs the
  "expect the largest jump" row.*

---

## Verify library behaviour, never from memory

A claim about what a dependency does is checked by running it, and the output goes
in the PR or the notes. Settled so far:

- `text-embedding-3-large` is **not bit-deterministic across batch positions**: the
  same string at a different position in the batch returns a vector differing up to
  1.3e-3 in the largest component, ~6e-4 in cosine. Enough to flip the order of two
  near-identical documents on a rebuild. Measured slice-0, `56aae62`.
- Census does **not** keep `B`/`C` five-digit stems aligned: `C25045` is the
  collapsed `B25044`, and no `C25044` exists. Twin-folding therefore matches on
  identical embedded text plus a strict cell-count majority, never on a shared
  stem. `56aae62`.
