# On Windows without `make`, run the underlying commands directly —
# every target here is one line on purpose.
#
# uv manages the environment. `uv run` syncs it first, so there is no venv to
# activate and no "works on my machine" gap with CI, which runs the same lines.

.PHONY: check eval demo gate lint types test fmt invariants hooks metadata index serve

## Fast gate. Must stay under 60 seconds or it stops getting run.
check: lint types test invariants
	uv run python scripts/check_budgets.py

## Retrieval scoreboard. No agent, no server, no Census key. Needs
## OPENAI_API_KEY and GEMINI_API_KEY: embed the query, then score retriever
## (@10) and selector (@1 with rerank.py).
eval:
	uv run python scripts/eval_retrieval.py --verbose
	uv run python scripts/eval_retrieval.py --tier long_tail --rerank
	uv run python scripts/score_synthetic.py

## Cache ACS metadata, then check every golden fixture against it. No keys.
metadata:
	uv run python scripts/fetch_metadata.py
	uv run python scripts/verify_golden.py

## Rebuild index_store/ from cached metadata. Needs OPENAI_API_KEY.
index:
	uv run python scripts/build_index.py

## End-to-end against live APIs. Needs OPENAI_API_KEY and CENSUS_API_KEY.
demo:
	uv run python scripts/run_demo.py --repeat 3

## Local API. Swagger at http://127.0.0.1:8000/docs
serve:
	uv run uvicorn src.main:app --reload

## Run one gate phase in a fresh context, transcript to evidence/slice-<N>/.
## Usage: make gate PHASE=gate2 SLICE=0 [ENGINE=cursor]. See docs/playbooks/run-slice.md.
gate:
	bash scripts/gate.sh $(PHASE) $(SLICE)

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
