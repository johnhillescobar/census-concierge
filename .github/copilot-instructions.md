# Census Concierge review instructions

Read `CLAUDE.md`, `AGENTS.md`, `docs/playbooks/review-pr.md`, and the matching catalog in `docs/requirements.md`, `docs/ask-path.md`, or `docs/retrieval.md` before reviewing a change.

## What to enforce

- Every data answer must include the full Census API URL, the estimate plus its 90% MOE, GEOID, universe, and relevant alternatives. An incomplete-geography refusal must return no URL, candidates, or fetch.
- Never infer geography, vintage, or scope from prose when structured intent is available. Validate structured intent downstream and never silently substitute a vintage or geography.
- Preserve redacted CensusURL handling. Never format or log a raw URL containing `&key=`.
- Do not introduce graph nodes for branching, modules named `*_manager`, `*_orchestrator`, `*_factory`, `*_policy`, `*_strategy`, or `*_service`, or abstractions before a second caller.
- Do not raise or lower budgets. A change must fit existing budgets and invariants.
- Prefer behavior tests and mutation checks. Do not assert on prompt wording or LLM prose.
- Verify the PR's user-facing claim, required evidence, Gate 1 and Gate 2 findings, and scope. Missing or failed AC/TC evidence means "Not yet".
- Findings should be action-oriented, specific to changed code, and ranked by severity. Do not report style-only findings or speculative issues.

## Required validation

For code reviews, account for failures in:

- `make check`
- `python scripts/check_budgets.py`
- `python scripts/check_invariants.py --base origin/main`
- The relevant mutation and E2E evidence

CI failures and silent wrong-answer risks block merge. Never read the sealed eval set or tune against it.
