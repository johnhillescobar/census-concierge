# Playbook: reviewing a PR

Canonical. `.claude/skills/review-pr/` and `.cursor/commands/review-pr.md` are
thin pointers to this file — edit here, not there.

## First: run the machines

Do not review by reading. Run these, and paste what they say.

```
uv run python scripts/check_budgets.py
uv run python scripts/check_invariants.py --base origin/main
uv run ruff check . && uv run ruff format --check .
uv run mypy api/src
uv run pytest -q -m "not integration"
```

**These are not advisory.** If any exits non-zero the review is over until it
does not. In particular, `check_invariants --base` catches the one thing that
matters most: a budget that was quietly widened to make the change fit.

Everything below is what the machines *cannot* check.

## The claim

**What can a user do now that they could not before?** One sentence, in the PR
description. If it cannot be written, the PR is refactoring or scaffolding — say
so plainly rather than dressing it as a feature.

**Is the evidence real?** `make eval` and `make demo` scoreboard quoted, not
paraphrased. Link the teed transcript; do not paste or Read it. A pass rate at
a stated `--repeat`, not a single run. This pipeline is nondeterministic; one
green run is not evidence, and "it works now" is not a number.

**At n=40, a move of under ~10 points in `retrieval@1` is noise.** A PR claiming
improvement on a delta smaller than that is claiming something the data does not
support. Say so.

## Scope

- Does the change belong to the current slice? If it belongs to a later one,
  name the slice and stop. Check the **Not in this slice** list.
- Under ~15 files touched, or an explanation why not.
- Was anything added "while we were in there"? That is how the predecessor grew.

## Silent-wrong-answer review

For any change touching a response path:

- **URL, MOE, GEOID, universe** still present in every branch, including the
  failure branches. A wrong URL is fixable in ten seconds; missing MOE is a
  professionally useless answer.
- Is `&key=` redacted on every path this change adds? Redaction is a property of
  the `CensusURL` type — if this PR formats a URL any other way, that is the
  finding.
- Do numbers ever pass back through the model? The model names
  `B01003_001E`; it must never handle the value.
- Did a guard become a blocking question? Guards warn and ship the answer. A
  user who does not know the table ecosystem *cannot answer* a clarification
  prompt — that is why there are none.
- Did anything start silently repairing input — a substituted vintage, a
  corrected geography? That is a warning on the answer, never an invisible fix.

## Shape

- New tool: which question does it answer, and is an existing tool also a
  plausible answer to that question? If so it is one tool with a parameter.
- New route: is it a tool wearing an endpoint costume?
- New Pydantic model: which of the three boundaries is it on? Per-row models are
  a no.
- New `.add_node()`: is it a durable checkpoint, or a branch the model should
  have made?
- Did the shape change without `docs/ARCHITECTURE.md` changing?

## Tests

- Behaviour, not wording. No assertions on prompt text or LLM prose.
- No fake that returns the same table for every input. The predecessor had one
  returning `B01003` unconditionally and it hid a broken retriever for months.
- A new test file is not evidence that anything works. `make demo` output is.

## The verdict

Say one of three things, and mean it:

1. **Ship it** — with the user-facing claim restated in your own words.
2. **Ship it with follow-ups** — list them; none may be silent-wrong-answer
   findings, which block.
3. **Not yet** — name the single most important reason first, not a list of
   twelve.
