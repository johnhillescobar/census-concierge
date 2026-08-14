# On Windows without `make`, run the underlying commands directly —
# every target here is one line on purpose.

.PHONY: check eval demo lint types test fmt

## Fast gate. Must stay under 60 seconds or it stops getting run.
check: lint types test
	python scripts/check_budgets.py

## Retrieval scoreboard. No API keys, no agent, no server.
eval:
	python scripts/eval_retrieval.py --verbose

## End-to-end against live APIs. Needs OPENAI_API_KEY and CENSUS_API_KEY.
demo:
	python scripts/run_demo.py --repeat 3

lint:
	ruff check api web

types:
	mypy api/src

test:
	pytest api/tests -q
