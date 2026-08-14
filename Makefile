# On Windows without `make`, run the underlying commands directly —
# every target here is one line on purpose.
#
# uv manages the environment. `uv run` syncs it first, so there is no venv to
# activate and no "works on my machine" gap with CI, which runs the same lines.

.PHONY: check eval demo lint types test fmt invariants hooks

## Fast gate. Must stay under 60 seconds or it stops getting run.
check: lint types test invariants
	uv run python scripts/check_budgets.py

## Retrieval scoreboard. No API keys, no agent, no server.
eval:
	uv run python scripts/eval_retrieval.py --verbose

## End-to-end against live APIs. Needs OPENAI_API_KEY and CENSUS_API_KEY.
demo:
	uv run python scripts/run_demo.py --repeat 3

## Mechanically checkable project rules. --base adds the budget-diff check.
invariants:
	uv run python scripts/check_invariants.py --base origin/main

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff check --fix .
	uv run ruff format .

types:
	uv run mypy api/src

test:
	uv run pytest -q -m "not integration"

## One-time setup.
hooks:
	uv run pre-commit install
