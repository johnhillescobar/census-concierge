# Ideation transcript

Verbatim record of the conversation that produced this project, beginning with
the ideation prompt. Preserved as written, typos included. Context: it followed
a review of the predecessor project `census_tool`, which reached 38,184 lines
across 116 files without reliably answering "what's the population of New York
City?".

Source: Claude Code session, 2026-08-11/12, model claude-opus-5.

---

## User

Let's assume that we want to create a brand new project for a census agent concierge. The agent would be a AI agent that would interact with the end user questions like in a conversation allocated in a canvas that would display the summary tables and graphs of each question on one side, where the user can ese the graphical componen of his questions, whereas the chat provides the natural language answer of it. The agent is intended to remember the conversation and follow up on it like asking clarification questions or refer to a previous point of the conversation. Then, once the conversation is complete, a pdf document with questions, questions answers, summary tables (when applicable), visualizations (if applicable), and the url shape of eact api call to the census bureau is there. The pdf would have both a table of content and a summary section. I think the project would be a multi-repo project -one for the frontend and another for the backend. Frontend would use Javascript, whereas the backend in Python. The project is NOT expected to only run locally but in an online. When online, the project would require an user to input credentials to have access. Given this, the solution should be able to run concurrently when multiple users are interacting with it. Since this an AI agent, I want to use OpenAI, Langchain, Langgraph, Langsmith or Langfuse,Pydantic (to guarantee the LLM answer is always validated and the agent receive the proper feedback to give a good and aligned answer)  and FastAPI as I want to be able to define APIs that I can use to interact with via Swagger and connect with the frontend. There is a radically important topic here: As I intend to develop with an AI IDE or CLI (Cursor or Claude), I need harnesses or mechanisms that prevent my project from derailing like this one. I'm a middle level developer, so there will be instances where I'd tend follow the AI agent advice, but I need that my project environment to be set in a way that we can do both: 1) have a grounded understanding of the architecture and the coding development agent receive immediate feedback when it start over engineering and/or drifting away from the expected goal. THIS LAST PART IS VERY VERY VERY VERY IMPORTANT TO AOVID MONTHS OF UNUSABLE FEATURE. Please, let's start discussing so that you can give me your input to tighten my ask for success.

## Assistant

Good — let me push on the ask before agreeing with it, because there's a problem in the first paragraph.

### The spec you just wrote is bigger than the one that died

Count what's in it: multi-repo, JS frontend, canvas artifact pane, conversational memory, clarification, follow-up reference resolution, PDF with TOC and summary, hosted deployment, authentication, multi-user concurrency, LangGraph, observability, Pydantic validation-feedback loops, FastAPI + Swagger.

The old project had *fewer* moving parts than that and it still buried you. If you build this spec front-to-back, you will be four months in with auth working, a canvas rendering placeholder tables, and no agent that reliably answers "what's the population of NYC."

So the first and most important harness isn't a lint rule. **It's that nothing on that list gets built until a single question round-trips end to end.** No mechanism catches "built the whole thing at once" — only sequencing does. I'll come back to this with a concrete slice plan.

Everything else below assumes the goal is right; I'm only arguing about order and enforcement.

### Where I'd change the architecture

**Monorepo, not multi-repo.** This is my strongest disagreement. Two repos for a solo mid-level dev buys you nothing and costs: version skew between API and client, two CI configs, two PRs for one feature, and contract drift that only shows up at runtime. Do this instead:

```
census-concierge/
  api/     FastAPI + agent (Python)
  web/     React/TS
  packages/client/   ← generated from FastAPI's OpenAPI schema
  Makefile, .github/workflows/
```

FastAPI already emits an OpenAPI spec. Generate the TypeScript client from it in CI and **fail the build if the checked-in client differs from the freshly generated one.** Now a breaking API change cannot merge without the frontend change in the same commit. That's a real anti-drift mechanism you get almost for free, and multi-repo makes it impossible.

Split later if a second team ever appears. It won't.

**Don't build auth.** Use Clerk, Auth0, or Supabase Auth. Hand-rolled session/credential handling for an internet-facing app is a category of bug you don't want to own, and it's zero percent of your product's value.

**Pick one observability tool, not "Langsmith or Langfuse."** Start with **LangSmith** — with LangChain/LangGraph it's an env var and nothing else, and on day one you need traces more than you need a pricing strategy. Move to Langfuse later if cost or self-hosting bites. Wiring both is a week you don't get back.

**Concurrency: this is where LangGraph actually earns its keep** — and where your old app would have fallen over. It used `checkpoints.db`, SQLite on local disk. Multi-user hosted means **Postgres checkpointer, `thread_id` per conversation, async endpoints, and zero module-level mutable state.** Flag for later: your old agent used a `set_grounded_execution_context` / `reset_grounded_execution_context` context-token pattern. Contextvars are async-safe *if* set and reset within one task, but that pattern is one refactor away from cross-user data leakage. In the new build, pass context as function arguments.

**PDF must be a background job.** Generating a document with charts and a TOC takes seconds to tens of seconds. Under a request-response handler that's a timeout and a blocked worker. `POST /reports` → job id → poll or SSE. Decide this now, because retrofitting async job handling is painful.

**Charts: have the agent emit a spec, not code.** A Pydantic `ChartSpec` (type, x, y, series, title) that the frontend renders. Never let the LLM emit plotting code or SVG — unreviewable, unverifiable, and a security problem the day you host it.

### The harness — the part you care about

Here's the diagnosis that everything else hangs off:

> **The old project didn't derail because the AI over-engineered. It derailed because the only feedback signal available was "tests pass," so that's what got optimized.** Your CLAUDE.md even says it: *"that path is how this repo got a green suite and no working product."*

An AI coding agent will maximize whatever signal you give it, relentlessly and without judgment. Give it green tests, you get 100 test files and 8 validators. Give it a user-value number, you get user value. So the harness is mostly about *which number is on the scoreboard.*

Five mechanisms, in order of how much they'll actually save you:

#### 1. Budgets file, enforced in CI

One file, checked in, machine-verified. Crude, unarguable, and impossible to rationalize past.

```yaml
# budgets.yaml — raising any number requires a separate human commit + reason
api_src_loc:        4000
api_src_files:        40
graph_nodes:           8
agent_tools:           6
domain_models:        15
direct_dependencies:  25
p95_latency_seconds:  20
max_file_loc:        400
```

The mechanic that makes it work: **the agent may never raise a budget.** If a change needs more, it stops and asks you. Raising a number is a standalone commit by you with a one-line reason. This turns "the codebase grew to 38k lines" from something that happens invisibly across 50 PRs into ~10 deliberate decisions you personally made and can read back.

You already invented this — *"baselines are a debt register that may only shrink."* It worked. The flaw was that it governed one narrow thing (hand-built dicts) instead of the dimensions that actually ballooned.

#### 2. The demo gate as the primary scoreboard

```
make demo     # runs 10 real questions, 3x each, prints pass rate + p95 latency
```

Output goes in `evidence/latest.json`, and **the PR template requires pasting it.** No pasted demo output, no merge. A ticket is not closed by passing tests — it's closed by a number moving.

Put the current number at the top of the README so it's the first thing you and the agent see. Make it the scoreboard.

The latency budget matters more than you'd think: every unnecessary node, every re-plan loop, every redundant LLM call costs seconds. Your old app hit 206 seconds on the simplest possible question. A p95 gate at 20s would have flagged the drift *months* before you felt it.

#### 3. Behavior tests only — question in, URL out

Your `census_url_fixtures.py` was the best file in the old repo. Generalize it:

```
question → expected (table_id, geography, year, full API URL)
```

That's the whole test suite for the agent. It survives refactors, it breaks on regressions, and it can't be gamed by restructuring internals. Three hard rules:

- Never assert on prompt wording or LLM prose (you learned this — it's in your CLAUDE.md).
- Never name a test file after a ticket. `test_census_43_turn1_table_selection.py` tests a *fix*; nobody will ever delete it or know what it's for.
- Fakes that return `B01003` for any input are banned from anything claiming to test retrieval.

#### 4. A short, *negative* architecture doc

Your existing CLAUDE.md is genuinely good — the Traps section especially. Its weakness is that it's advisory prose, so drift accumulates without tripping anything. Keep it under 100 lines and make it mostly prohibitions:

```
- One graph. Nodes only for durable checkpoints, not for branching logic.
- No module named *_manager, *_orchestrator, *_factory, *_policy, *_strategy.
- No validator that validates another validator's output.
- No abstraction until a second caller exists. Inline it until then.
- The URL is the product. Every answer renders it, including failures.
```

That fourth line is worth its weight. And on the third — your old repo shipped `plan_validator`, `grounded_plan_validator`, `plan_result_validator`, `variable_validator`, `dataset_geography_validator`, plus three validation *tools*. Eight validation modules. No one decided that; it accreted one reasonable-seeming PR at a time.

#### 5. A diff-size tripwire

Any PR touching more than ~15 files is a redesign wearing a feature's clothes. Have CI comment loudly. You don't have to block it — you just have to *see* it, because this is precisely the change you'd otherwise skim and approve.

### Slice plan

Each slice ends in a demo you can show someone. Nothing from slice N+1 starts until N is demoed.

| # | Slice | Done when |
|---|---|---|
| 0 | `POST /ask` → `{answer, url, rows}`. No UI, no auth, no graph, no memory. Plain tool-calling loop, 4 tools. | You `curl` it and get a working Census URL |
| 1 | Minimal chat UI, single pane | You type in a browser and get an answer |
| 2 | Canvas pane: table + `ChartSpec` rendering | Two panes working |
| 3 | Memory: `thread_id`, Postgres checkpointer, follow-ups | "What about Texas?" resolves against the prior turn |
| 4 | PDF export as a background job | You download a real document |
| 5 | Auth + hosted deploy | Someone else logs in and uses it |

Slice 0 is one to two weeks and is 80% of the product's value. Auth is last because it protects something that must exist first.

Note what's *not* in the list: clarification. Build it only when the demo suite shows you which questions genuinely need it — and expect that number to be small once retrieval is solid. Last time, clarification became a 43-file subsystem substituting for retrieval that didn't work.

### What I need from you to tighten this further

1. **Salvage or clean slate?** I'd port `geography_registry.py`, `census_api_utils.py`, the URL fixtures, and the Chroma index builders — copied in deliberately, file by file, not `git mv`'d wholesale. Anything you drag over unexamined brings its assumptions with it.
2. **How many users, realistically?** Ten known people vs. public signup changes auth, hosting, and cost controls a lot. If it's ten, slice 5 shrinks dramatically.
3. **Who's the first real user, and when do they touch it?** If there's a specific census nerd who'll try slice 1 and complain, that's worth more than every mechanism above. Real user feedback is the anti-drift harness; the rest is scaffolding for when they're not looking.

Want me to draft the actual scaffold next — `budgets.yaml`, the CI workflow that enforces it, the PR template, the CLAUDE.md, and the `make demo` harness — so you can see whether these gates feel livable before you commit to them?

---

## User

1. clean slate as I mentioned new project; 2) it could be initially 10 but it can be more once the app proves its value; 3) census nerds means people who actively work with census data, as census data have some many tables, the idea is to help the user to find in a conversational way and help them extract insights, usually they geo spatial professionals, non-profit researchers, among other

## Assistant

Answer 3 is the most useful thing you've told me, and it changes the product more than the other two combined.

### Your users are experts, and that inverts several defaults

GIS professionals and non-profit researchers already know what a table ID is. They know ACS from decennial. They've been burned by geography hierarchies. That means:

**Blocking clarification questions are the wrong interaction.** For a novice, "Did you mean New York City or New York State?" is helpful. For someone who does this daily, it's a speed bump — and it's exactly the subsystem that ate your last project. The expert-appropriate pattern is a **visible, editable plan**: the agent shows what it chose as a compact editable strip in the canvas —

```
ACS 5-Year 2019–2023  ·  B01003  ·  county  ·  Texas (48)     [edit]
```

— and runs. Wrong table? They fix it in one click, faster than reading your question. This is strictly better than conversational clarification for this audience, and it's *far* less code: one component and an "re-run with overrides" endpoint, versus ten files and a resume-path in your graph. Reserve real blocking questions for the genuinely ambiguous case, and let the demo suite tell you how often that actually is.

**Margins of error are not optional.** This is the one that'll decide whether researchers trust the tool. Every ACS estimate variable `B01003_001E` has a companion `B01003_001M`. A researcher comparing two tracts cannot use your output at all if you drop the MOE — the difference may not be statistically distinguishable. If your tool returns bare estimates, it is a toy to this audience. So: **always fetch and display `E` and `M`, and flag when a difference isn't significant at 90%.** Small geographies especially — tract and block-group MOEs are often huge relative to the estimate.

**Guard the overlapping-vintage trap.** Comparing ACS 2015–2019 against 2018–2022 is statistically invalid — Census says so explicitly — and it is a mistake working researchers make constantly. An agent that catches it earns credibility in one interaction. That is what domain value looks like here, and it's about 20 lines.

**Always return GEOID.** Geospatial folks will join your output to TIGER shapefiles. Bare place names are useless for that; the concatenated FIPS is the whole point. Include it in every table, every CSV.

**CSV export before PDF.** These users will pull the data into ArcGIS, R, or pandas. That's a day-one need and it's near-free. The PDF is the *session artifact* — the thing they hand to a program officer or attach to a grant report — which is valuable but comes later.

**Reframe worth deciding now:** experts don't ask independent questions, they refine. *"Population by county in Texas"* → *"add median income"* → *"just counties over 100k"* → *"now 2019 too."* That's one dataset being iterated, not four cards. Your canvas description assumes a stack of per-question panels; the alternative is a living working table with question history alongside. It's a fork in your state model, so pick it before slice 2 — I lean toward the working-table model for this audience, but it's genuinely your call and it depends on whether you see sessions as exploration or as report-building.

### What answers 1 and 2 change

**Clean slate — agreed, with one exception.** Don't port code. But do write down, fresh, the ~30 golden question→URL fixtures as a spec file before you write the agent. Not ported code: a re-derived specification. It costs an afternoon, it's your entire test suite, and going in without it means rediscovering by trial and error which geographies ACS5 supports at tract level. The knowledge is the asset; the code isn't.

**10 users now, more later — build stateless, not scaled.** Concretely: Postgres from day one (never SQLite — it's the thing that would have blocked you anyway), no module-level mutable state so you can run N workers, one container behind a managed host. Skip queues, caching layers, and horizontal scaling until someone complains. The one thing to add early is a **per-user spend cap** — 10 researchers running county-level sweeps against GPT-4-class models will surprise you on the invoice, and a cap is 20 lines now versus an incident later.

Also: at 10 known users, slice 5 shrinks to almost nothing. Clerk free tier, email allowlist, done in an afternoon.

### Where that leaves the plan

Two changes to the slice order from my last message:

- **Slice 0 gains MOE + GEOID** in the response contract. They're cheap now and structural later.
- **Slice 2 gains the editable plan strip and CSV export**, and clarification drops off the roadmap entirely until the demo suite proves it's needed.

---

I think the ask is tight enough to build against now. The remaining question is just where to start, and I'd suggest the harness rather than the code — because if the gates don't exist on day one, slice 0 will quietly become slice 0 through 4.

Want me to draft the scaffold? Concretely that's: `budgets.yaml` + the CI script that enforces it, `CLAUDE.md`, the PR template with the demo-output requirement, `make demo` with a starter question set, and the golden-fixtures spec file. I'd write it to the scratchpad first so you can read it before anything lands in a real project directory — tell me where you want it to live if you'd rather it go straight there.

---

## User

This is not true and I have witnessed this in real life: "GIS professionals and non-profit researchers already know what a table ID is. They know ACS from decennial. They've been burned by geography hierarchies". They tend to be expert in a subset of tables, but they can struggle finding other tables or expanding insights. Census data is not 10 tables, is a ecosystem of tables that can be difficult to navigate

## Assistant

You're right, and that's a correction that moves the center of the product. Narrow-and-deep expertise means the gap isn't "help me phrase my query" — it's **"I don't know what exists outside my corner."** Someone who knows B19013 cold may have never touched housing, commuting, or disability tables, and won't know the subject tables exist at all.

So discovery isn't a supporting feature behind the agent. **Retrieval quality is the product.** Which means the part of your last project that got the least real work — and was faked in tests with a stub returning `B01003` for everything — is the part the new one lives or dies on.

### What that means for retrieval

Semantic search over table titles alone will not work. Census titles are terse jargon: `MEDIAN HOUSEHOLD INCOME IN THE PAST 12 MONTHS (IN 2023 INFLATION-ADJUSTED DOLLARS)`. Nobody types that. Four things to build into the index:

**Index the universe, not just the title.** "Households" vs. "families" vs. "population" vs. "housing units" is the single most common source of wrong-but-plausible answers, and it trips experts the moment they step outside their subset. The universe belongs in the embedded text and in what you show the user.

**Index at variable level as well as table level.** Users often want one line inside a large cross-tab they'd never find by table name.

**Generate synthetic questions at index time.** For each table, have an LLM write 5–10 questions it answers, and embed those alongside the metadata. Matching a user's natural question against *other natural questions* works dramatically better than matching it against Census title-case. This is a build-time cost you pay once, and it's probably the highest-leverage thing in the whole retrieval stack.

**Hybrid search, not pure vectors.** BM25 or plain lexical matching for exact IDs and jargon, embeddings for semantic. Your users *will* type "B19013" and "gross rent as a percentage of income," and vectors handle the first badly.

### What it changes in the interface

**Return alternatives as results, not as a question.** This is the bit that shifts most. If the user doesn't know the ecosystem, "which table did you mean?" is literally unanswerable — they can't choose from a list of things they've never seen. But this works:

```
Used: B19013 · Median Household Income · universe: households

Related:  B19001  income brackets (distribution, not median)
          B19113  median FAMILY income (different universe)
          B19013B median household income, Black householder
          S1901   income profile (pre-computed percentages)
```

That's the concierge behavior, it directly serves "expand insights," and every answer teaches one more corner of the ecosystem. Note this *strengthens* the case against a clarification subsystem rather than weakening it — showing candidates beats asking a question the user can't answer.

**Surface table families.** The A–I race iterations, B vs. C (collapsed) vs. S (subject) vs. DP (profile) — that structure is invisible to someone outside their specialty and is exactly what they need pointed out.

### What it changes in your metric

Your demo suite has to be **deliberately long-tail**, or it will measure nothing. If the fixtures are population and median income, you're recreating the `B01003`-for-everything fake with extra steps.

Spread the ~30 golden questions across corners nobody's expert in all of: commuting (B08301), housing cost burden (B25070), broadband access (B28002), disability (B18101), veterans (B21001), language spoken at home (C16001), plus subject and profile tables. And split the pass criterion in two, because they fail differently and you'll want to know which:

```
retrieval@1   correct table selected
answered      correct URL + data returned
p95 latency
```

`retrieval@1` on long-tail questions becomes the number on your scoreboard. It's the one that actually tracks whether you're building the product you described.

---

Everything else from the last two messages stands — MOE, GEOID, the vintage-overlap guard, the editable strip, monorepo, slice order. The correction sharpens where the engineering effort goes: **index construction and retrieval evaluation, not orchestration.** Which is a good thing to learn before writing code, given that the last build put its effort in the opposite place.

One consequence worth flagging now: a build-time index over ACS metadata with synthetic questions is a real component with its own cost and refresh cycle, and it needs its own eval harness separate from the agent's. I'd make that slice 0 — before the agent exists, before FastAPI. If retrieval@1 on long-tail questions is bad, nothing downstream can save it, and you'll know in a week rather than in month four.

Shall I draft the scaffold now with retrieval eval as its centerpiece, or do you want to keep pulling on the retrieval design first?

---

## User

The rest of your assessment is correct. Thanks for providing it as you manage to articulate what I was looking for is much more articulate way

## Assistant

*(Drafted the scaffold: `budgets.toml`, `scripts/check_budgets.py`, `scripts/eval_retrieval.py`, `evals/golden_questions.toml`, `CLAUDE.md`, `.github/pull_request_template.md`, `Makefile`, `README.md` — then ran both scripts.)*

Both scripts run. Here's the scaffold, in `scratchpad/concierge-scaffold/`:

```
budgets.toml                      the limits, with the "never raise these" rule
scripts/check_budgets.py          enforcer — LOC, files, nodes, tools, models, deps, latency
scripts/eval_retrieval.py         retrieval@1 / @5 / MRR, broken out by tier
evals/golden_questions.toml       30 questions — 4 core, 18 long-tail, 8 traps
CLAUDE.md                         short, mostly prohibitions
.github/pull_request_template.md  demo output required to merge
Makefile                          check / eval / demo
README.md                         scoreboard at the top
```

**The most useful property showed up by accident.** With nothing built, `check_budgets.py` exits 1:

```
  ok    api src LOC                 0 <= 4000
  ok    graph nodes                 0 <= 8
  FAIL  retrieval_at_1              0 >= 0.7
```

The build is red on day zero, and it's red for the *right reason* — the product's core capability doesn't exist yet. Every structural budget is green because nothing's been built; the only thing failing is the thing that matters. That inverts the incentive your last project had, where the suite went green long before the product worked. Here you cannot get to green by writing code — only by making retrieval work.

Three things you should know before trusting any of it:

**The table IDs in `golden_questions.toml` were written from memory and need verifying against the live groups endpoint.** I flagged it at the top of the file. A wrong fixture is worse than no fixture — it trains you to "fix" correct behavior. That's an hour of work and it's the highest-value hour in slice 0.

**`run_demo.py` isn't written.** It needs an app to demo. `check_budgets.py` already reads the fields it will write (`p95_latency_seconds`, `answered_rate`), so it slots in at slice 1 without changes.

**No CI workflow yet** — I'd rather write that once the repo's actual shape and package manager are settled than guess.

On the budget numbers: they're deliberately tight, and 4,000 LOC will feel constraining around slice 3. That's intended. Raising it should be a decision you make and write a reason for, roughly ten times over the project's life, rather than something that happens invisibly across fifty PRs.

Two questions before this goes anywhere real:

1. **Where should it live?** I'd suggest `C:\Users\johnh\Dropbox\Python\census-concierge\` as a sibling to the old project — but I won't create a directory in your Dropbox without you saying so.
2. **Do the gates feel livable?** Specifically the PR template. It's the one that'll chafe on a Tuesday when you just want to merge a small fix, and a gate you route around is worse than no gate. If it's too heavy, better to cut it now than discover you've been skipping it.

---

## User

What do you mean by this? Your demo suite has to be deliberately long-tail and retrieval@1 on long-tail questions becomes the number on your scoreboard

## Assistant

Two separate ideas bundled in one sentence. Let me take them apart.

### retrieval@1

Mechanically: run each eval question through your retriever, get back a ranked list of tables, and ask *was the correct one ranked first?* Retrieval@1 is the fraction where it was.

`eval_retrieval.py` also reports @5 and MRR, and the gap between them is the useful part:

- **@5 low** → the index is broken. The right table isn't surfacing at all, no matter how you rank. Fix the indexed content — universe text, variable labels, synthetic questions.
- **@5 high but @1 low** → the index is fine, the ranking is wrong. Fix with a reranker or hybrid scoring. Much cheaper problem.

But **@1 is the one on the scoreboard**, because your agent acts on the top hit. A right answer sitting at rank 4 is a wrong answer to the user. @5 is diagnostic; @1 is the product.

### "Deliberately long-tail"

Here's the definition that matters:

> **A question belongs in your eval set if the user couldn't already answer it themselves.**

If a researcher knows the table is B19013, they don't need your product — they go to data.census.gov and pull it in two minutes. So every question in your eval where the user already knows the answer is a question that doesn't measure your product's value.

The trap is that easy questions score well and feel like progress. Look at the lexical distance:

```
"What's the population of Harris County?"
  → B01003  TOTAL POPULATION
     "population" appears verbatim. Keyword matching gets this.

"How many people bike to work in Portland?"
  → B08301  MEANS OF TRANSPORTATION TO WORK
     Zero overlap. "bike" is a value inside the table, not in its name.

"Which counties have the worst broadband access?"
  → B28002  PRESENCE AND TYPES OF INTERNET SUBSCRIPTIONS IN HOUSEHOLD
     Neither "broadband" nor "access" appears anywhere in the title.
```

A retriever that nails the first and misses the other two would score **100% on a core-only eval** and be useless for your actual users. That's not hypothetical — it's what your last project did. `grounded_planning_fakes.py` returned `B01003` for any input, tests built on it passed, and a broken retriever stayed hidden for months. A core-heavy eval set is the same failure with extra steps: you're testing that your embedding model can match a word to itself.

### Building the set

Don't hand-pick from memory the way I did in `golden_questions.toml` — that biases toward tables you already know, which is exactly the bias you're trying to escape. Better, in rough order of value:

1. **Ask 3–5 actual census nerds for the last ten questions they struggled with.** This is worth more than everything below it.
2. **Sample programmatically.** Pull the ACS group list, sample across topic prefixes (B08 transport, B18 disability, B25 housing, B27 health, B28 internet…), then write a natural question for each table you land on.
3. **Use the lookup heuristic:** if *you* had to look up the table ID to write the fixture, it belongs in the long-tail tier. If you knew it cold, it's core.

### Why it's the scoreboard

Three reasons:

**It's causal.** Retrieval → right table → right URL → right answer. Everything downstream is plumbing. At retrieval@1 of 40%, no prompt engineering, no graph node, no validation layer rescues the product. At 85%, a mediocre agent still delivers real value. There's no other number with that property.

**It's cheap.** No LLM calls for the retrieval step, no Census API, no server, no frontend. Seconds to run. Cheap enough for every commit — which is what makes it a feedback loop instead of a report you generate quarterly.

**It's honest early.** You can measure it in week one, before any of the architecture exists. If long-tail retrieval can't clear 70%, you've learned the product is hard for a reason unrelated to anything you were about to spend four months building.

One caveat: with only 18 long-tail questions, you *will* overfit if you tune against them repeatedly. Grow the set as you go, and hold back a handful you don't look at until you think you're done.

---

## User

let's do this. 1) Create the directory you suggested. Then, in the new .claude folder: 1) create a DESIGN and PLAN documents, 2) A verbatim copy of this conversation from my long prompt (ideation prompt to start a new project). Once finished on this, I need you to create the .cursor needed files to align with your architecture. I'll be working with Claude and Cursor.

*(This document, `DESIGN.md`, `PLAN.md`, and the `.cursor/` rules were produced in response.)*
