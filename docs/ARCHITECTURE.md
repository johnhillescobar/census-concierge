# ARCHITECTURE — the system as it IS

**Status: nothing is built. Slice 0 has not started.**

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
scripts/eval_retrieval.py    the scoreboard — runs against a stub, scores 0
evals/golden_questions.toml  42 questions; expect_table values UNVERIFIED
evidence/latest.json         last measured run
docs/playbooks/review-pr.md  canonical review procedure
pyproject.toml               uv workspace root; ruff + mypy + pytest config
api/pyproject.toml           the app's dependencies (3 so far)
.github/workflows/check.yml  the gate, on every PR
.github/workflows/build-index.yml  manual; publishes the index release asset
```

`api/src/` exists but is empty. No `web/`, no index, no agent, no server, no
database. `build-index.yml` will fail until `scripts/build_index.py` exists —
it is manual-dispatch only, so nothing runs it by accident.

`check_budgets.py` currently exits 1 on `retrieval_at_1: 0 (limit 0.7)`. That is
the intended state: the build is red on day zero for the right reason, and it
cannot be turned green by writing code — only by making retrieval work.

## What each slice adds here

Fill these in as they ship. Delete this list when it is no longer a list of
futures.

| slice | adds to this file |
|---|---|
| 0 | the index: corpus, layers, artifacts, how it is built and loaded |
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
