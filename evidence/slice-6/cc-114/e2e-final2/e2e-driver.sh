#!/bin/bash
cd /c/Users/johnh/Dropbox/Python/census-concierge/.claude/worktrees/e2e-3945694
O=out; L=$O/log.txt
echo "HEAD start $(git rev-parse HEAD)" >> $L
run() { n=$1; shift; echo "$n START $(date -u +%FT%TZ) :: $*" >> $L; "$@" > $O/$n.out 2> $O/$n.err; rc=$?; echo "$n END $(date -u +%FT%TZ) rc=$rc" >> $L; }
run a uv run python scripts/eval_retrieval.py --verbose
run b uv run python scripts/eval_retrieval.py --tier long_tail --rerank
run c uv run python scripts/score_synthetic.py
run d uv run python scripts/run_demo.py --repeat 3
cp evidence/latest.json $O/latest-after-demo.json
run e uv run python scripts/run_grid.py --repeat 3
cp evidence/latest.json $O/latest-after-grid.json; cp evidence/grid-latest.json $O/ 2>/dev/null; cp -r evidence/grid* $O/ 2>/dev/null
run f uv run python scripts/check_budgets.py
run g uv run python scripts/check_invariants.py --base origin/main
echo "HEAD end $(git rev-parse HEAD)" >> $L
echo DONE >> $L
