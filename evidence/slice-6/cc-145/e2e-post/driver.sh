#!/bin/bash
# CC-145 post-merge E2E on merged main 117d08b. Owed because the merge touched the Makefile, a
# run-harness file in closure.py E2E_PATHS (the gate -> brief recipe; no eval or demo recipe line
# changed). The make eval and make demo recipes, in recipe order, each command's output redirected
# to its own file (no tee). Transcripts are never read; aggregates come from evidence/latest.json
# (gated keys and demo.misses only) and from scripts/metric_compare.py. Same driver as CC-143.
cd "$(dirname "$0")/../../../.."
unset VIRTUAL_ENV
O=evidence/slice-6/cc-145/e2e-post; L=$O/log.txt
echo "HEAD start $(git rev-parse HEAD) branch $(git branch --show-current) status: $(git status --short | wc -l) changed" >> $L
run() { n=$1; shift; echo "$n START $(date -u +%FT%TZ) :: $*" >> $L; "$@" > $O/$n.out 2> $O/$n.err; rc=$?; echo "$n END $(date -u +%FT%TZ) rc=$rc" >> $L; }
run s uv sync
run v uv run python scripts/verify_golden_places.py
run n1 npm --prefix web ci
run n2 npm --prefix web run build
run a uv run python scripts/eval_retrieval.py --verbose
run b uv run python scripts/eval_retrieval.py --tier long_tail --rerank
run c uv run python scripts/score_synthetic.py
run d uv run python scripts/run_demo.py --repeat 3
cp evidence/latest.json $O/latest-after-demo.json
run e uv run python scripts/run_grid.py --repeat 3
cp evidence/latest.json $O/latest-after-grid.json; cp evidence/grid-latest.json evidence/grid-trials.jsonl $O/ 2>/dev/null
run f uv run python scripts/check_budgets.py
run g uv run python scripts/check_invariants.py --base origin/main
echo "HEAD end $(git rev-parse HEAD) status: $(git status --short -- api/src scripts/run_demo.py pyproject.toml uv.lock | wc -l) measured paths changed" >> $L
echo DONE >> $L
