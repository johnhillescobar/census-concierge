# census-concierge

Helps people who work with Census data find tables **outside their specialty**
and pull them into a working dataset, conversationally.

Users are GIS professionals and non-profit researchers. They are expert in a
handful of tables and lost in the other thousand. The product is *discovery*.

## Definition of done

```
make demo        # real questions, real API, prints pass rate and p95 latency
```

Done means a user got an answer. Paste the output in the PR. A passing pytest
run is not done. A new test file is not done. A closed ticket is not done.

**This pipeline is nondeterministic.** One run tells you nothing — compare rates
at the same `--repeat`. Current numbers live in `evidence/latest.json` and at
the top of the README.

## Budgets are enforced

`budgets.toml` caps lines, files, graph nodes, tools, models, dependencies and
latency. `make check` fails the build when one is exceeded.

**Never raise a budget.** If a change does not fit, say so and ask. Raising a
limit is a human commit with a written reason. This is the only mechanism
protecting the project from the failure it exists to avoid: a predecessor
reached 38,000 lines and 116 files without answering "population of New York
City" in under 75 seconds.

## The URL is the product

Every answer renders the full Census API URL — variables, geography, vintage —
including when the fetch fails or the agent is unsure. A user handed a URL that
returns the wrong table fixes it in ten seconds. A user handed prose cannot.

Also non-negotiable in every response:

- **Margins of error.** Fetch `M` alongside every `E`. ACS estimates without
  MOE are professionally useless to a researcher, and small-geography MOEs
  routinely swamp the differences people want to compare.
- **GEOID.** They join to TIGER shapefiles. Names do not.
- **Universe.** "Households" vs "families" vs "population" vs "housing units"
  is the most common silent wrong answer in Census work.
- **Alternatives.** Show related tables, not just the pick. That is the whole
  concierge value, and it teaches the ecosystem one answer at a time.

## Do not

- Ask a blocking clarification question. Users who do not know the ecosystem
  **cannot answer one.** Show candidates as results with an editable plan strip.
  Clarification machinery ate a third of the predecessor's codebase.
- Add a graph node for branching. Nodes are durable checkpoints only.
- Create a module named `*_manager`, `*_orchestrator`, `*_factory`, `*_policy`,
  `*_strategy`, or `*_service`.
- Add a validator that validates another validator's output. The predecessor
  shipped eight validation modules; nobody decided that.
- Introduce an abstraction before a second caller exists. Inline it.
- Name a test after a ticket. `test_census_43_turn1_table_selection.py` tests a
  fix nobody can later interpret or delete.
- Assert on prompt wording or LLM prose. Those tests break on edits and survive
  regressions.
- Let the LLM emit chart code or SVG. It emits a `ChartSpec`; the frontend renders.
- Compare overlapping ACS 5-year vintages (2015-2019 vs 2018-2022). Warn instead.

## Jira — status source of truth

Project **`CC`** at `johnhillescobar.atlassian.net`. Ticket status lives in Jira, not
chat. Close with `uv run python scripts/jira_transition.py CC-N --done --comment "…"`
(needs `ATLASSIAN_EMAIL` + `ATLASSIAN_API_TOKEN` in `.env`). Use the script, not IDE
MCP — same path in Claude Code and Cursor.

Jira owns *open vs done* and the post-merge numbers. `.claude/PLAN.md` STATUS
is a close pointer (floors, `evidence/slice-<N>/`, epic URL), not an eval ledger.
Name `CC-N` in commits/PRs; Jira comments link to the PR or `evidence/`.

## Slice workflow

One pipeline per slice: **pre-flight** (run every technical claim before coding) ->
implement -> **Gate 1** (matrix tests, every new test mutation-checked) -> **Gate
2** (cold review: `/code-review` then `docs/playbooks/review-pr.md`) -> fix ->
**E2E** (`make eval` / `make demo`, transcript in the PR) -> merge -> **E2E again**
against merged `main`. Every phase persists to git / the PR / `evidence/slice-<N>/`
and **Jira** before the next; a fresh context rebuilds from those, never from chat
history. Full procedure: `docs/playbooks/run-slice.md` or the `run-slice` skill;
matrix and worked examples: `docs/process-evidence.md`.

## Traps

- A retrieval fake that returns the same table for any input tests nothing.
  The predecessor had one and it hid a broken retriever for months.
- `success` on an API response describes the HTTP call, not whether the question
  was answered. Keep those two concepts in separate fields, always.
- Census URLs carry `&key=`. Redact at the boundary — these reach logs,
  telemetry, PDFs and git.
- `core` questions in the golden set prove nothing. `long_tail` is the metric.

## Architecture

One tool-calling loop. Four to six tools. LangGraph only where durable
checkpointing and multi-user resumption genuinely require it — not for routing.

Postgres from day one (never SQLite: multi-user). No module-level mutable
state; pass context as arguments so workers scale horizontally. PDF generation
is a background job, never a request handler.

`docs/ARCHITECTURE.md` is one page and describes the system as it *is*. If you
change the shape, update it in the same commit.

## Environment

**uv** manages the environment; **ruff** lints and formats. Python is pinned to
**3.12** and CI runs the same version — on this machine, Windows Smart App
Control blocks unsigned native extensions in the uv-managed 3.13 build, which
breaks `_sqlite3` and `uuid_utils`. That cost real time once already.

```
make check     # lint + types + tests + invariants + budgets, under 60s
make eval      # retrieval scoreboard; needs OPENAI_API_KEY to embed the query
make demo      # end-to-end against live APIs; needs OPENAI_API_KEY, CENSUS_API_KEY
make hooks     # one-time: install pre-commit
```

Every target is `uv run …` on one line, so they work on Windows without `make`.

Two gates, and neither is advisory:

- `scripts/check_budgets.py` counts things against `budgets.toml`.
- `scripts/check_invariants.py` checks that specific mistakes were not made.
  With `--base origin/main` it also fails when a budget was **weakened** —
  a raised ceiling or a lowered floor. That is the check this repo exists for.

Reviewing a change: `docs/playbooks/review-pr.md`, or the `review-pr` skill.
