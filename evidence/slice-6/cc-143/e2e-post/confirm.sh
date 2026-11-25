#!/bin/bash
# CC-143 post-merge, the one confirmation run the playbook allows after a red row that no owner
# exception covers (run-slice.md, "A red post-merge row", step 2). Same head, same recipes for what
# the comparator judges: make eval, then the demo at --repeat 3. The grid is not judged by the
# comparator and is not repeated. Output to files only; transcripts are never read.
cd "$(dirname "$0")/../../../.."
O=evidence/slice-6/cc-143/e2e-post; L=$O/log.txt
echo "CONFIRM HEAD start $(git rev-parse HEAD) branch $(git branch --show-current) measured paths changed: $(git status --short -- api/src scripts/run_demo.py pyproject.toml uv.lock | wc -l)" >> $L
run() { n=$1; shift; echo "$n START $(date -u +%FT%TZ) :: $*" >> $L; "$@" > $O/$n.out 2> $O/$n.err; rc=$?; echo "$n END $(date -u +%FT%TZ) rc=$rc" >> $L; }
run v2 uv run python scripts/verify_golden_places.py
run a2 uv run python scripts/eval_retrieval.py --verbose
run b2 uv run python scripts/eval_retrieval.py --tier long_tail --rerank
run c2 uv run python scripts/score_synthetic.py
run d2 uv run python scripts/run_demo.py --repeat 3
cp evidence/latest.json $O/latest-confirm.json
run f2 uv run python scripts/check_budgets.py
echo "CONFIRM HEAD end $(git rev-parse HEAD) measured paths changed: $(git status --short -- api/src scripts/run_demo.py pyproject.toml uv.lock | wc -l)" >> $L
echo CONFIRM DONE >> $L
