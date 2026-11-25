"""CC-143: run the command behind every AC and TC and save its raw output, one file per id.

    uv run python evidence/slice-6/cc-143/closure_run.py

Run from the repository root at the head under test. It writes evidence/slice-6/cc-143/
closure-run/<ID>.txt and HEAD.txt, and nothing else. A row that waits for the owner or for the
merge is listed in WAITING and gets no file: its status in the manifest is NOT RUN.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

OUT = Path("evidence/slice-6/cc-143/closure-run")
MC = "api/tests/test_metric_compare.py"
GATE = "api/tests/test_closure_gate.py"
INV = "api/tests/test_invariants.py"
BUD = "api/tests/test_budgets.py"
RUNS = [f"evidence/metrics/runs/{n}.json" for n in ("main-b1", "main-b2", "cc104-p1", "cc104-p2")]
PY = ["uv", "run", "python"]

# id -> the commands whose output proves it. A (file, [tests]) pair is one pytest run.
ROWS: dict[str, list[object]] = {
    "AC1": [
        [*PY, "scripts/metric_compare.py", "noise", *RUNS, "--sizes", "1x1,2x2"],
        (
            MC,
            [
                "test_unchanged_code_seldom_fails_its_own_simulated_reruns",
                "test_a_seeded_regression_is_caught_more_often_the_larger_it_is",
                "test_a_broken_question_in_a_simulated_run_is_never_answered",
                "test_a_simulated_run_takes_its_scalars_from_one_stored_run",
                "test_stored_same_code_comparisons_are_observed_each_way_at_a_size_they_can_fill",
                "test_the_noise_report_gives_each_rate_an_interval_and_says_what_cannot_be_observed",
                "test_the_wilson_interval_holds_the_rate_and_narrows_with_more_trials",
                "test_the_noise_command_reads_its_sizes",
            ],
        ),
    ],
    "AC2": [
        (
            MC,
            [
                "test_pooled_runs_are_judged_as_one_sample",
                "test_a_pool_keeps_every_trial_and_averages_what_each_run_reports",
                "test_pools_of_different_sizes_compare_rates_not_counts",
                "test_a_pool_whose_runs_have_different_indexes_is_not_comparable",
                "test_candidate_files_are_pooled_against_same_window_main_files",
                "test_the_planned_number_of_runs_per_side_is_required",
                "test_base_runs_must_be_clean_runs_of_one_head_on_main",
                "test_base_runs_scored_by_another_scorer_are_not_a_baseline",
                "test_the_compare_command_takes_pooled_files_and_judges_against_l_by_default",
                "test_the_stored_candidate_runs_are_pooled_against_the_stored_main_runs",
                "test_pooled_candidate_runs_must_have_measured_one_head",
                "test_the_same_run_given_twice_is_not_two_runs",
                "test_base_runs_must_measure_the_main_the_candidate_is_built_on",
                "test_runs_collected_outside_the_window_are_not_same_window",
                "test_the_ledger_row_names_every_run_file_by_hash",
            ],
        ),
    ],
    "AC3": [
        [*PY, "scripts/metric_compare.py", "freeze"],
        (
            MC,
            [
                "test_freeze_prints_the_hashes_and_every_rule_number",
                "test_every_rate_row_is_judged_by_a_number_in_the_committed_rule",
                "test_every_row_compare_prints_is_a_rate_with_a_rule_or_a_named_hard_failure",
                "test_a_fall_inside_the_tolerance_passes_and_one_past_it_fails",
                "test_more_empty_answers_than_the_tolerance_fail",
                "test_questions_returning_fewer_rows_when_answered_fail_past_their_limit",
                "test_a_retrieval_or_selector_drop_fails_past_its_tolerance",
                "test_a_p95_rise_past_its_tolerance_fails_and_one_inside_it_passes",
                "test_a_group_under_the_minimum_gets_a_verdict_from_the_small_group_number",
                "test_the_selector_tolerance_is_divided_by_the_runs_pooled_on_the_smaller_side",
                "test_a_tolerance_that_is_not_a_finite_number_excuses_nothing",
            ],
        ),
    ],
    "AC4": [
        [*PY, "scripts/check_invariants.py", "--base", "origin/main"],
        (
            GATE,
            [
                "test_every_rule_parameter_in_the_committed_protocol_is_guarded",
                "test_raising_a_rule_tolerance_fails_and_lowering_it_is_allowed",
                "test_a_rule_number_that_is_removed_or_not_a_number_fails",
                "test_a_rule_parameter_the_guard_does_not_know_is_a_violation",
                "test_a_rule_number_main_does_not_have_yet_is_the_owners_to_ratify",
                "test_a_reference_may_leave_the_report_only_list_and_never_join_it",
                "test_loosening_the_frozen_protocol_fails",
                "test_tightening_the_frozen_protocol_is_allowed",
            ],
        ),
    ],
    "AC5": [
        ["git", "ls-files", "-s", "evidence/metrics/runs"],
        (
            MC,
            [
                "test_the_four_stored_runs_are_two_codes_each_measured_twice",
                "test_both_stored_same_code_pairs_pass_either_way_round",
                "test_a_stored_run_with_the_stated_number_of_long_tail_questions_broken_fails",
            ],
        ),
    ],
    "AC6": [
        (
            MC,
            [
                "test_a_run_collected_before_a_rule_change_is_judged_under_the_new_rule",
                "test_a_run_collected_under_other_collection_settings_is_refused",
                "test_the_collection_hash_ignores_the_rule_and_moves_with_what_a_run_collects",
                "test_a_stored_run_collected_before_the_rule_existed_is_judged_under_todays_rule",
                "test_only_an_explicit_legacy_flag_skips_the_collection_check",
            ],
        ),
    ],
    "AC10": [
        (
            MC,
            [
                "test_the_question_level_rule_names_every_question_of_a_broken_geography",
                "test_the_question_level_rule_fires_on_unchanged_main_at_one_run_per_side",
                "test_the_question_level_rule_blocks_when_each_side_pools_two_runs",
                "test_a_question_lost_in_both_pooled_runs_fails_a_verdict_the_rates_would_pass",
            ],
        ),
    ],
    "AC11": [
        (
            GATE,
            [
                "test_a_ticket_that_merged_no_product_eval_or_harness_file_closes_without_a_post_merge_run",
                "test_what_owes_a_post_merge_run_is_the_product_the_evals_and_the_run_harness",
                "test_code_merged_in_one_pull_request_is_seen_when_the_manifest_lands_in_another",
                "test_a_change_committed_straight_onto_the_base_is_read_with_the_series_it_landed_in",
                "test_a_branch_that_landed_as_a_fast_forward_is_read_whole",
                "test_a_file_moved_out_of_the_product_tree_owes_the_run",
                "test_a_tested_head_spelled_short_or_in_capitals_is_the_same_commit",
                "test_work_that_is_not_on_the_base_cannot_close_without_a_run",
                "test_a_merge_git_cannot_diff_owes_the_run",
                "test_a_half_recorded_post_merge_run_is_not_waved_through",
                "test_check_file_names_the_manifest_whose_merges_are_diffed",
            ],
        ),
    ],
    "AC12": [
        [*PY, "scripts/check_budgets.py", "--structural-only"],
        ["git", "diff", "origin/main", "--", "docs/playbooks/run-slice.md"],
    ],
    "TC1": [(MC, ["test_both_stored_same_code_pairs_pass_either_way_round"])],
    "TC2": [
        ["git", "log", "--format=%h %ad %s", "--date=iso", "-S", "BROKEN_LONG_TAIL = 6", "--", MC],
        ["git", "log", "--format=%h %ad %s", "--date=iso", "-S", "rate_drop_max", "--", "evals"],
        (MC, ["test_a_stored_run_with_the_stated_number_of_long_tail_questions_broken_fails"]),
    ],
    "TC3": [(MC, ["test_a_named_hard_failure_blocks_even_when_the_pooled_rate_rises"])],
    "TC4": [
        (
            MC,
            [
                "test_a_group_under_the_minimum_gets_a_verdict_from_the_small_group_number",
                "test_a_small_group_is_not_judged_by_the_large_group_tolerance",
            ],
        )
    ],
    "TC5": [
        (
            MC,
            [
                "test_a_missing_or_failing_a_or_a0_does_not_change_the_verdict",
                "test_a_failing_blocking_reference_still_fails_beside_a_passing_anchor",
                "test_l_is_judged_whatever_references_are_named",
            ],
        )
    ],
    "TC6": [
        (
            INV,
            [
                "test_a_floor_exception_added_in_a_change_fails_the_check",
                "test_an_exception_whose_baseline_or_ticket_changed_is_a_new_exception",
            ],
        )
    ],
    "TC7": [
        (
            GATE,
            [
                "test_a_change_to_l_outside_the_owners_own_commit_is_rejected",
                "test_seeding_l_is_the_owners_own_commit_too",
            ],
        ),
        (MC, ["test_what_promote_writes_is_still_the_owners_to_commit"]),
    ],
    "TC8": [(GATE, ["test_a_ticket_whose_merge_touched_api_src_still_owes_its_post_merge_run"])],
}
# Code for these is tested (AC7: the promote and guard tests; AC8: test_budgets.py), but the
# criterion itself is an owner commit or the post-merge run.
WAITING = {
    "AC7": "the owner seeds L on main after the merge (owner-commits.md, step 3)",
    "AC8": "the owner records the exceptions in budgets.toml (owner-commits.md, step 1)",
    "AC9": "the owner ratifies in two commits (owner-commits.md, steps 1 and 2)",
    "AC13": "the post-merge run on main, judged against L",
}


def run(command: list[str]) -> tuple[int, str]:
    done = subprocess.run(
        command, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return (
        done.returncode,
        f"$ {' '.join(command)}\n{done.stdout}{done.stderr}[exit {done.returncode}]\n",
    )


def only_the_protocol_awaits_the_owner(code: int, text: str) -> bool:
    """`check_invariants --base origin/main` on this branch: green, or red on exactly the one check
    that reserves the [rule] numbers for the owner. Any other failing check, or a traceback, is a
    failure of AC4's command and not the expected refusal."""
    failing = {
        line.split()[1:] and " ".join(line.split()[1:])
        for line in text.splitlines()
        if line.startswith("  FAIL  ")
    }
    return code == 0 or (code == 1 and failing == {"protocol weakened"} and "Traceback" not in text)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    dirty = subprocess.run(["git", "status", "--short"], capture_output=True, text=True).stdout
    (OUT / "HEAD.txt").write_text(f"{head}{dirty or 'clean\n'}", encoding="utf-8", newline="\n")
    red = []
    for name, commands in ROWS.items():
        parts = []
        for command in commands:
            if isinstance(command, tuple):
                path, tests = command
                # by node id: pytest exits non-zero when a named test does not exist, where
                # `-k` would quietly run the ones that do
                nodes = [f"{path}::{test}" for test in tests]
                command = ["uv", "run", "pytest", *nodes, "-q", "-rA", "-p", "no:cacheprovider"]
            code, text = run(list(command))  # type: ignore[arg-type]
            parts.append(text)
            if "check_invariants.py" in " ".join(command):
                failed = not only_the_protocol_awaits_the_owner(code, text)
            else:
                failed = bool(code)
            if failed:
                red.append(name)
        (OUT / f"{name}.txt").write_text("\n".join(parts), encoding="utf-8", newline="\n")
        print(f"{name:<5} {'RED' if name in red else 'ok'}")
    for name, why in WAITING.items():
        print(f"{name:<5} NOT RUN: {why}")
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
