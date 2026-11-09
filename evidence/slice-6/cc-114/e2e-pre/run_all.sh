cd "$(dirname "$0")/../../../.."
D=evidence/slice-6/cc-114/e2e-pre
run(){ n=$1; shift; echo "START $n $(date +%T) :: $*" >> $D/codes.log; "$@" > $D/$n 2>&1; echo "EXIT $n $? $(date +%T)" >> $D/codes.log; }
run eval-1.txt uv run python scripts/eval_retrieval.py --verbose
run eval-2.txt uv run python scripts/eval_retrieval.py --tier long_tail --rerank
run eval-3.txt uv run python scripts/score_synthetic.py
run demo.txt uv run python scripts/run_demo.py --repeat 3
run grid.txt uv run python scripts/run_grid.py --repeat 3
echo ALLDONE >> $D/codes.log
