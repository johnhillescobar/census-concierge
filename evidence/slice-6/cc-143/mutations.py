# ruff: noqa: E501  (the code being replaced is quoted as it stands)
"""CC-143 Gate 1: revert one behaviour at a time and show that its tests fail.

    uv run python evidence/slice-6/cc-143/mutations.py            # run every mutation
    uv run python evidence/slice-6/cc-143/mutations.py --check    # only check that each applies

Run from the root of a clean checkout that nothing else is using: each mutation edits one file,
runs only the tests named for it, and restores the file. GOOD means the test failed against the
broken behaviour; BAD means it still passed, so it does not check what it claims. A mutation is
named for the behaviour it reverts. At the end, every test this branch adds (a name that
origin/main does not have) must have at least one GOOD.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

MC, CI = "scripts/metric_compare.py", "scripts/check_invariants.py"
CL, CB, PR = "scripts/closure.py", "scripts/check_budgets.py", "evals/metric_protocol.toml"
M, G = "api/tests/test_metric_compare.py", "api/tests/test_closure_gate.py"
B, I = "api/tests/test_budgets.py", "api/tests/test_invariants.py"  # noqa: E741
RATE = 'status = "PASS" if worse <= limit + EPS else "FAIL"'
EXCUSE = (
    'if entry["metric"] == limit and sign * (value - entry["baseline"]) <= rule[tolerance] + EPS:'
)
LOST = (
    "if all(map(_answered, base.trials[cohort_name][family])) and not any(map(_answered, trials))"
)
DRAWN = "pooled[family] = [(not dead and pick[0], pick[1]) for pick in picks]"

# (the behaviour reverted, file, text, replacement, {test file: [tests that must fail]})
MUTATIONS: list[tuple[str, str, str, str, dict[str, list[str]]]] = [
    (
        "a rate row never fails",
        MC,
        RATE,
        'status = "PASS"',
        {
            M: [
                "test_a_fall_inside_the_tolerance_passes_and_one_past_it_fails",
                "test_a_p95_rise_past_its_tolerance_fails_and_one_inside_it_passes",
                "test_questions_returning_fewer_rows_when_answered_fail_past_their_limit",
                "test_more_empty_answers_than_the_tolerance_fail",
                "test_a_retrieval_or_selector_drop_fails_past_its_tolerance",
                "test_a_stored_run_with_the_stated_number_of_long_tail_questions_broken_fails",
                "test_candidate_files_are_pooled_against_same_window_main_files",
                "test_a_failing_blocking_reference_still_fails_beside_a_passing_anchor",
                "test_a_seeded_regression_is_caught_more_often_the_larger_it_is",
                "test_l_is_judged_whatever_references_are_named",
            ]
        },
    ),
    (
        "any fall fails, as before this ticket",
        MC,
        RATE,
        'status = "PASS" if worse <= EPS else "FAIL"',
        {
            M: [
                "test_a_fall_inside_the_tolerance_passes_and_one_past_it_fails",
                "test_both_stored_same_code_pairs_pass_either_way_round",
                "test_unchanged_code_seldom_fails_its_own_simulated_reruns",
                "test_the_noise_report_gives_each_rate_an_interval_and_says_what_cannot_be_observed",
                "test_stored_same_code_comparisons_are_observed_each_way_at_a_size_they_can_fill",
                "test_a_candidate_inside_the_tolerance_passes_compare_and_still_cannot_lower_l",
                "test_a_group_under_the_minimum_gets_a_verdict_from_the_small_group_number",
            ]
        },
    ),
    (
        "a tie fails",
        MC,
        RATE,
        'status = "PASS" if worse < 0 else "FAIL"',
        {
            M: [
                "test_a_run_compared_with_itself_passes",
                "test_pools_of_different_sizes_compare_rates_not_counts",
                "test_the_same_run_given_twice_is_not_two_runs",
            ]
        },
    ),
    (
        "a tolerance that is not a number passes everything",
        MC,
        RATE,
        'status = "FAIL" if worse > limit + EPS else "PASS"',
        {M: ["test_a_tolerance_that_is_not_a_finite_number_excuses_nothing"]},
    ),
    (
        "a small group is judged by the large-group tolerance",
        MC,
        'limit = rule["small_group_lost_questions"] / len(mine) if small else rule["rate_drop_max"]',
        'limit = rule["rate_drop_max"]',
        {
            M: [
                "test_a_small_group_is_not_judged_by_the_large_group_tolerance",
                "test_a_group_under_the_minimum_gets_a_verdict_from_the_small_group_number",
            ]
        },
    ),
    (
        "a rate row does not say how much worse the candidate is",
        MC,
        'kind="rate", worse=round(worse, 6)',
        'kind="rate"',
        {
            M: [
                "test_a_rate_row_says_how_much_worse_the_candidate_is",
                "test_pools_of_different_sizes_compare_rates_not_counts",
                "test_an_unanswered_trial_is_not_a_question_returning_fewer_rows",
                "test_a_run_of_small_losses_never_moves_l",
                "test_the_stored_candidate_runs_are_pooled_against_the_stored_main_runs",
            ]
        },
    ),
    (
        "a question's rows are averaged over every trial, answered or not",
        MC,
        "got = [rows for answered, rows in trials if answered]",
        "got = [rows for answered, rows in trials]",
        {M: ["test_an_unanswered_trial_is_not_a_question_returning_fewer_rows"]},
    ),
    (
        "a pool reports its first run's scalars",
        MC,
        "scalars={k: sum(run.scalars[k] for run in runs) / len(runs) for k in sorted(shared)},",
        "scalars=dict(runs[0].scalars),",
        {M: ["test_a_pool_keeps_every_trial_and_averages_what_each_run_reports"]},
    ),
    (
        "a pool keeps only its last run's trials",
        MC,
        'pooled[family] += [(bool(t["answered"]), int(t.get("rows") or 0)) for t in items]',
        'pooled[family] = [(bool(t["answered"]), int(t.get("rows") or 0)) for t in items]',
        {
            M: [
                "test_pooled_runs_are_judged_as_one_sample",
                "test_a_pool_keeps_every_trial_and_averages_what_each_run_reports",
                "test_the_stored_candidate_runs_are_pooled_against_the_stored_main_runs",
                "test_a_reference_registered_from_two_runs_is_judged_as_their_pool",
            ]
        },
    ),
    (
        "pooled runs may have different indexes",
        MC,
        'if len(indexes) != 1 or "" in indexes:',
        'if "" in indexes:',
        {M: ["test_a_pool_whose_runs_have_different_indexes_is_not_comparable"]},
    ),
    (
        "the planned number of runs per side is not required",
        MC,
        "if (len(cands), len(base_paths)) != want:",
        "if False:",
        {M: ["test_the_planned_number_of_runs_per_side_is_required"]},
    ),
    (
        "base runs need not be clean runs of one head on main",
        MC,
        "if len(heads) != 1 or not head or not clean or not _reachable(head, MAIN):",
        "if not head:",
        {M: ["test_base_runs_must_be_clean_runs_of_one_head_on_main"]},
    ),
    (
        "the base's scorer is not compared with the candidate's",
        MC,
        'if not recorded or any(theirs[k] != judged[k] for k in ("scorer", "cohorts", "collection")):',
        "if not recorded:",
        {M: ["test_base_runs_scored_by_another_scorer_are_not_a_baseline"]},
    ),
    (
        "one run given twice among the candidate and main runs is pooled as two",
        MC,
        "    if duplicated([*cands, *bases]):",
        "    if False:",
        {M: ["test_the_same_run_given_twice_is_not_two_runs"]},
    ),
    (
        "one candidate run given twice is not flagged without a base",
        MC,
        "    if duplicated(cands):",
        "    if False:",
        {M: ["test_the_same_run_given_twice_is_not_two_runs"]},
    ),
    (
        "any clean run of main is a baseline, whatever the candidate is built on",
        MC,
        "if not mine or not _built_on(head, mine):",
        "if not mine:",
        {M: ["test_base_runs_must_measure_the_main_the_candidate_is_built_on"]},
    ),
    (
        "the product code is not compared when asking what a candidate is built on",
        MC,
        'return _git_status("diff", "--quiet", base_head, fork.stdout.strip(), "--", *MEASURED) == 0',
        "return True",
        {M: ["test_whether_a_candidate_is_built_on_a_base_is_asked_of_real_git"]},
    ),
    (
        "runs from different windows are judged together",
        MC,
        "if hours is None or not hours <= window + EPS:",
        "if False:",
        {M: ["test_runs_collected_outside_the_window_are_not_same_window"]},
    ),
    (
        "naming another reference leaves L out",
        MC,
        'return ["L", *(name for name in ref_names if name != "L")]',
        'return list(ref_names) or ["L"]',
        {M: ["test_l_is_judged_whatever_references_are_named"]},
    ),
    (
        "A and A0 block",
        MC,
        'row.blocking = row.blocking and name not in protocol["rule"]["report_only"]',
        "row.blocking = bool(row.blocking)",
        {
            M: [
                "test_a_missing_or_failing_a_or_a0_does_not_change_the_verdict",
                "test_report_only_rows_are_printed_in_parentheses",
            ]
        },
    ),
    (
        "a report-only row is printed like a blocking one",
        MC,
        'status = c.status if c.blocking else f"({c.status})"',
        "status = c.status",
        {M: ["test_report_only_rows_are_printed_in_parentheses"]},
    ),
    (
        "the verdict counts rows that are only reported",
        MC,
        "(c.status for c in checks if c.blocking)",
        "(c.status for c in checks)",
        {
            M: [
                "test_a_missing_or_failing_a_or_a0_does_not_change_the_verdict",
                "test_the_question_level_rule_is_not_adopted_because_it_fires_on_unchanged_main",
            ]
        },
    ),
    (
        "an excepted floor fails the verdict",
        MC,
        '"EXCEPTED": 0',
        '"EXCEPTED": 3',
        {M: ["test_an_excepted_floor_does_not_block_while_no_worse_than_its_baseline"]},
    ),
    (
        "an exception excuses any value, however far below its baseline",
        MC,
        EXCUSE,
        'if entry["metric"] == limit:',
        {
            M: [
                "test_an_excepted_floor_does_not_block_while_no_worse_than_its_baseline",
                "test_each_quality_floor_is_excepted_by_its_own_rule_number",
            ],
            B: [
                "test_an_over_ceiling_p95_is_excepted_while_no_worse_than_the_owners_baseline",
                "test_main_fails_a_floor_that_fell_past_its_exception",
            ],
        },
    ),
    (
        "an exception for one floor covers every floor",
        MC,
        EXCUSE,
        'if sign * (value - entry["baseline"]) <= rule[tolerance] + EPS:',
        {
            M: ["test_an_exception_covers_only_its_own_metric"],
            B: ["test_an_exception_for_one_floor_does_not_cover_another"],
        },
    ),
    (
        "a malformed exception does not stop the others from excusing",
        MC,
        '    if exception_problems(budgets):\n        return ""\n',
        "",
        {
            M: ["test_a_malformed_exception_excuses_nothing"],
            B: ["test_a_malformed_exception_is_itself_a_failure_and_excuses_nothing"],
        },
    ),
    (
        "exceptions are never honoured",
        MC,
        "    _section, tolerance, sign = EXCEPTABLE[limit]",
        '    return ""\n    _section, tolerance, sign = EXCEPTABLE[limit]',
        {
            M: [
                "test_an_excepted_floor_does_not_block_while_no_worse_than_its_baseline",
                "test_each_quality_floor_is_excepted_by_its_own_rule_number",
            ],
            B: [
                "test_main_labels_an_excepted_quality_floor_and_counts_it",
                "test_an_over_ceiling_p95_is_excepted_while_no_worse_than_the_owners_baseline",
            ],
        },
    ),
    (
        "the selector floor is excepted by the answered-rate tolerance",
        MC,
        '"selector_at_1_min": ("quality", "selector_drop_max", -1),',
        '"selector_at_1_min": ("quality", "rate_drop_max", -1),',
        {M: ["test_each_quality_floor_is_excepted_by_its_own_rule_number"]},
    ),
    (
        "floors are judged on the first pooled run",
        MC,
        "value = None if None in values else sum(values) / len(values)  # type: ignore[arg-type]",
        "value = values[0]",
        {M: ["test_floors_are_judged_on_the_pooled_candidate"]},
    ),
    (
        "the p95 ceiling is judged on the first pooled run",
        MC,
        'pooled = percentile([float(t["latency_s"]) for run in cands for t in run.trials], 95)',
        'pooled = percentile([float(t["latency_s"]) for run in cands[:1] for t in run.trials], 95)',
        {M: ["test_floors_are_judged_on_the_pooled_candidate"]},
    ),
    (
        "the response contract is checked on the first pooled run",
        MC,
        'returned = [t for run in cands for t in run.trials if t.get("rows")]',
        'returned = [t for run in cands[:1] for t in run.trials if t.get("rows")]',
        {M: ["test_an_answer_missing_a_contract_field_fails"]},
    ),
    (
        "what a run reports is checked against its trials for the first pooled run only",
        MC,
        "for run in cands:  # what each run reports must be its own trials'",
        "for run in cands[:1]:",
        {
            M: [
                "test_a_p95_that_disagrees_with_its_trials_fails",
                "test_a_reported_answered_rate_that_the_trials_do_not_support_fails",
            ]
        },
    ),
    (
        "an answer missing a contract field passes",
        MC,
        '"PASS" if not bad else "FAIL",',
        '"PASS",',
        {M: ["test_a_named_hard_failure_blocks_even_when_the_pooled_rate_rises"]},
    ),
    (
        "the comparator ignores the owner's one-run waiver",
        MC,
        'waiver = budget_log.p95_waiver(_budgets_text(), one.at, pooled) if one else ""',
        'waiver = ""',
        {M: ["test_the_comparator_honours_a_one_run_waiver_as_the_budget_check_does"]},
    ),
    (
        "a one-run waiver covers a pool",
        MC,
        "one = cands[0] if len(cands) == 1 and pooled > ceiling else None",
        "one = cands[0] if pooled > ceiling else None",
        {M: ["test_the_comparator_honours_a_one_run_waiver_as_the_budget_check_does"]},
    ),
    (
        "the question-level rule always blocks",
        MC,
        'blocking=bool(rule["lost_questions_block"]),',
        "blocking=True,",
        {
            M: [
                "test_the_question_level_rule_is_not_adopted_because_it_fires_on_unchanged_main",
                "test_both_stored_same_code_pairs_pass_either_way_round",
            ]
        },
    ),
    (
        "the question-level rule never blocks",
        MC,
        'blocking=bool(rule["lost_questions_block"]),',
        "blocking=False,",
        {M: ["test_the_question_level_rule_blocks_once_the_owner_adopts_it"]},
    ),
    (
        "one answered reference trial is enough to call a question lost",
        MC,
        LOST,
        LOST.replace("if all(map(", "if any(map(", 1),
        {M: ["test_the_question_level_rule_is_not_adopted_because_it_fires_on_unchanged_main"]},
    ),
    (
        "lost questions are looked for in the long tail only",
        MC,
        LOST,
        LOST + ' and cohort_name == "long_tail"',
        {M: ["test_the_question_level_rule_names_every_question_of_a_broken_geography"]},
    ),
    (
        "a cohort with no questions divides by zero",
        MC,
        "        if not mine:  # nothing was asked, so nothing was measured",
        "        if False:",
        {M: ["test_a_cohort_with_no_questions_is_unknown_not_a_crash"]},
    ),
    (
        "empty answers are judged by the answered-rate tolerance",
        MC,
        '        rule["empty_rise_max"],',
        '        rule["rate_drop_max"],',
        {M: ["test_more_empty_answers_than_the_tolerance_fail"]},
    ),
    (
        "no question may return fewer rows",
        MC,
        '        rule["rows_lost_questions_max"],',
        "        0,",
        {M: ["test_questions_returning_fewer_rows_when_answered_fail_past_their_limit"]},
    ),
    (
        "retrieval is judged by the selector's tolerance",
        MC,
        "limit = rule[RATE_ROWS[key]]",
        'limit = rule["selector_drop_max"]',
        {M: ["test_a_retrieval_or_selector_drop_fails_past_its_tolerance"]},
    ),
    (
        "p95 may not rise at all",
        MC,
        '    limit = rule["p95_rise_max_seconds"]',
        "    limit = 0.0",
        {M: ["test_a_p95_rise_past_its_tolerance_fails_and_one_inside_it_passes"]},
    ),
    (
        "promotion needs A registered",
        MC,
        '    if "L" not in refs:',
        '    if "A" not in refs or "L" not in refs:',
        {M: ["test_promotion_needs_no_pass_against_a"]},
    ),
    (
        "promotion goes ahead with no L to judge against",
        MC,
        '    if "L" not in refs:',
        "    if False:",
        {M: ["test_promotion_is_refused_until_l_is_seeded"]},
    ),
    (
        "promotion may lower L",
        MC,
        '    if final != "PASS" or below:',
        '    if final != "PASS":',
        {
            M: [
                "test_a_run_of_small_losses_never_moves_l",
                "test_a_candidate_inside_the_tolerance_passes_compare_and_still_cannot_lower_l",
            ]
        },
    ),
    (
        "promotion ignores a failing verdict",
        MC,
        '    if final != "PASS" or below:',
        "    if below:",
        {M: ["test_a_candidate_that_fails_against_l_does_not_become_l"]},
    ),
    (
        "promotion stores only the first run of a pool",
        MC,
        'entry = build_entry(paths, produced, "accepted post-merge reference", legacy=False)',
        'entry = build_entry(paths[:1], produced, "accepted post-merge reference", legacy=False)',
        {M: ["test_a_pool_of_post_merge_runs_is_promoted_as_one_reference"]},
    ),
    (
        "pooled candidate runs may have measured different heads",
        MC,
        '    if any(str(run.hashes["head"]) != head for run in cands):',
        "    if False:",
        {M: ["test_pooled_candidate_runs_must_have_measured_one_head"]},
    ),
    (
        "an unstamped run is overlooked when the first pooled run is stamped",
        MC,
        "    if not all(run.hashes for run in cands):",
        "    if not cands[0].hashes:",
        {M: ["test_a_run_with_no_provenance_is_unknown_and_can_never_be_promoted"]},
    ),
    (
        "the candidate's collection settings are not checked",
        MC,
        '    elif actual["collection"] != now["collection"]:',
        "    elif False:",
        {M: ["test_a_run_collected_under_other_collection_settings_is_refused"]},
    ),
    (
        "a reference's collection settings are not checked",
        MC,
        '    if old["protocol"] != "legacy" and old.get("collection") != judged["collection"]:',
        "    if False:",
        {
            M: [
                "test_only_an_explicit_legacy_flag_skips_the_collection_check",
                "test_a_run_collected_under_other_collection_settings_is_refused",
            ]
        },
    ),
    (
        "a legacy reference is checked like any other",
        MC,
        '    if old["protocol"] != "legacy" and old.get("collection") != judged["collection"]:',
        '    if old.get("collection") != judged["collection"]:',
        {
            M: [
                "test_only_an_explicit_legacy_flag_skips_the_collection_check",
                "test_a_legacy_run_is_registered_without_reading_the_protocol_at_its_head",
            ]
        },
    ),
    (
        "a run is bound to the whole protocol file, rule included",
        MC,
        '    if any(run.hashes[k] != actual[k] for run in cands for k in ("scorer", "cohorts")):',
        '    if any(run.hashes[k] != actual[k] for run in cands for k in ("scorer", "cohorts", "protocol")):',
        {
            M: [
                "test_a_run_collected_before_a_rule_change_is_judged_under_the_new_rule",
                "test_a_stored_run_collected_before_the_rule_existed_is_judged_under_todays_rule",
            ]
        },
    ),
    (
        "the collection hash covers the rule",
        MC,
        "    return _digest(picked)",
        '    return _digest({**picked, "rule": protocol.get("rule")})',
        {
            M: [
                "test_the_collection_hash_ignores_the_rule_and_moves_with_what_a_run_collects",
                "test_a_stored_run_collected_before_the_rule_existed_is_judged_under_todays_rule",
            ]
        },
    ),
    (
        "the collection hash ignores the trials per question",
        MC,
        '("sampling", ("repeat", "blocks", "stopping", "exclusions")),',
        '("sampling", ("blocks", "stopping", "exclusions")),',
        {M: ["test_the_collection_hash_ignores_the_rule_and_moves_with_what_a_run_collects"]},
    ),
    (
        "a reference stores only its first run",
        MC,
        "    paths = _pool(run_paths)\n    runs = [load_run(path) for path in paths]\n    if not legacy:",
        "    paths = _pool(run_paths)[:1]\n    runs = [load_run(path) for path in paths]\n    if not legacy:",
        {M: ["test_a_reference_registered_from_two_runs_is_judged_as_their_pool"]},
    ),
    (
        "only the first file of a pooled reference is pinned",
        MC,
        "        for item in files\n",
        "        for item in files[:1]\n",
        {M: ["test_a_reference_registered_from_two_runs_is_judged_as_their_pool"]},
    ),
    (
        "a reference may name a head its runs did not measure",
        MC,
        'if not all(stamps) or any(s["head"] != head or s["dirty"] is not False for s in stamps):',
        "if False:",
        {M: ["test_a_reference_is_registered_only_from_clean_runs_of_the_head_it_names"]},
    ),
    (
        "a reference may pool one run twice",
        MC,
        "        if duplicated(runs):",
        "        if False:",
        {M: ["test_a_reference_is_registered_only_from_clean_runs_of_the_head_it_names"]},
    ),
    (
        "registering a legacy run reads the protocol at its head",
        MC,
        "    now = hashes(head) if legacy else judged_by(head)",
        "    now = judged_by(head)",
        {M: ["test_a_legacy_run_is_registered_without_reading_the_protocol_at_its_head"]},
    ),
    (
        "the ledger row leaves out the base files",
        MC,
        '"base": [_file_record(path) for path in base_paths],',
        '"base": [],',
        {M: ["test_the_ledger_row_names_every_run_file_by_hash"]},
    ),
    (
        "compare judges A, A0, L and B unless told otherwise",
        MC,
        'cmp_.add_argument("--refs", default="L")',
        'cmp_.add_argument("--refs", default="A,A0,L,B")',
        {M: ["test_the_compare_command_takes_pooled_files_and_judges_against_l_by_default"]},
    ),
    (
        "the compare command drops the base files",
        MC,
        "return cmd_compare(args.runs, names, targets, args.record, args.base)",
        "return cmd_compare(args.runs, names, targets, args.record, [])",
        {M: ["test_the_compare_command_takes_pooled_files_and_judges_against_l_by_default"]},
    ),
    (
        "a target is judged against the candidate itself",
        MC,
        "rows += target_check(cands, reference, protocol, cohort_name, goal)",
        "rows += target_check(cands, cands, protocol, cohort_name, goal)",
        {M: ["test_a_target_is_judged_against_the_reference_the_rows_were"]},
    ),
    (
        "freeze leaves out the rule numbers",
        MC,
        'print(f"  rate  {row:<28} {key} = {rule[key]:g}")',
        'print(f"  rate  {row:<28} {key}")',
        {M: ["test_freeze_prints_the_hashes_and_every_rule_number"]},
    ),
    (
        "the p95 row has no rule on record",
        MC,
        '    "p95 vs reference": "p95_rise_max_seconds",\n',
        "",
        {
            M: [
                "test_every_rate_row_is_judged_by_a_number_in_the_committed_rule",
                "test_every_row_compare_prints_is_a_rate_with_a_rule_or_a_named_hard_failure",
            ]
        },
    ),
    (
        "the run-count failure is not a named hard row",
        MC,
        '    "run count",\n',
        "",
        {M: ["test_every_row_compare_prints_is_a_rate_with_a_rule_or_a_named_hard_failure"]},
    ),
    (
        "a broken question still answers in a simulated run",
        MC,
        DRAWN,
        "pooled[family] = [(pick[0], pick[1]) for pick in picks]",
        {
            M: [
                "test_a_seeded_regression_is_caught_more_often_the_larger_it_is",
                "test_a_broken_question_in_a_simulated_run_is_never_answered",
            ]
        },
    ),
    (
        "a broken question returns no rows in a simulated run",
        MC,
        DRAWN,
        "pooled[family] = [(not dead and pick[0], 0 if dead else pick[1]) for pick in picks]",
        {M: ["test_a_broken_question_in_a_simulated_run_is_never_answered"]},
    ),
    (
        "a simulated run blends the stored runs' scalars",
        MC,
        "picked = [src.scalars[rng.randrange(len(src.scalars))] for _ in range(runs)]",
        "picked = list(src.scalars)",
        {M: ["test_a_simulated_run_takes_its_scalars_from_one_stored_run"]},
    ),
    (
        "a stored same-code pair is judged one way round only",
        MC,
        "[(left, right), (right, left)] if size[0] == size[1] else [(left, right)]",
        "[(left, right)]",
        {M: ["test_stored_same_code_comparisons_are_observed_each_way_at_a_size_they_can_fill"]},
    ),
    (
        "a pair judged both ways counts as two observations",
        MC,
        "        out.append(sorted(failing))",
        "        out.extend([sorted(failing)] * 2)",
        {
            M: [
                "test_stored_same_code_comparisons_are_observed_each_way_at_a_size_they_can_fill",
                "test_the_noise_report_gives_each_rate_an_interval_and_says_what_cannot_be_observed",
            ]
        },
    ),
    (
        "the noise report misstates how many more runs a size needs",
        MC,
        "{sum(size) - largest} more run(s) of that code",
        "{sum(size)} more run(s) of that code",
        {M: ["test_the_noise_report_gives_each_rate_an_interval_and_says_what_cannot_be_observed"]},
    ),
    (
        "one stored run is taken as enough for a noise report",
        MC,
        "    if largest < 2:",
        "    if largest < 1:",
        {M: ["test_the_noise_report_gives_each_rate_an_interval_and_says_what_cannot_be_observed"]},
    ),
    (
        "the interval has no width",
        MC,
        "    z = 1.959964",
        "    z = 0.0",
        {M: ["test_the_wilson_interval_holds_the_rate_and_narrows_with_more_trials"]},
    ),
    (
        "the noise command reports one size unless told",
        MC,
        '"--sizes", default="1x1,2x2", help=',
        '"--sizes", default="1x1", help=',
        {M: ["test_the_noise_command_reads_its_sizes"]},
    ),
    (
        "a run file is read without its stamp",
        MC,
        "hashes={k: stamp[k] for k in PROVENANCE_KEYS} if whole else {},",
        "hashes={},",
        {M: ["test_the_four_stored_runs_are_two_codes_each_measured_twice"]},
    ),
    (
        "the proposed rate tolerance is tighter than the stored same-code spread",
        PR,
        "rate_drop_max = 0.07 ",
        "rate_drop_max = 0.05 ",
        {M: ["test_both_stored_same_code_pairs_pass_either_way_round"]},
    ),
    (
        "the proposed rate tolerance is too loose for the stated defect",
        PR,
        "rate_drop_max = 0.07 ",
        "rate_drop_max = 0.09 ",
        {M: ["test_a_stored_run_with_the_stated_number_of_long_tail_questions_broken_fails"]},
    ),
    # --- scripts/check_invariants.py -------------------------------------------------------
    (
        "a rule tolerance may be raised",
        CI,
        "        elif after > before:",
        "        elif False:",
        {G: ["test_raising_a_rule_tolerance_fails_and_lowering_it_is_allowed"]},
    ),
    (
        "a rule number main does not have needs no owner",
        CI,
        'flag(f"[rule] {key}", f"new rule number {after:g}: the owner ratifies it")',
        "pass",
        {G: ["test_a_rule_number_main_does_not_have_yet_is_the_owners_to_ratify"]},
    ),
    (
        "a missing rule number is accepted",
        CI,
        'flag(f"[rule] {key}", "the rule number is missing or not a number")',
        "continue",
        {G: ["test_a_rule_number_that_is_removed_or_not_a_number_fails"]},
    ),
    (
        "nan and inf are accepted as limits",
        CI,
        "return float(value) if math.isfinite(value) else None  # nan or inf is not a limit",
        "return float(value)",
        {G: ["test_a_rule_number_that_is_removed_or_not_a_number_fails"]},
    ),
    (
        "a rule parameter the guard does not know is accepted",
        CI,
        'flag(f"[rule] {key}", "a rule parameter no invariant guards")',
        "pass",
        {G: ["test_a_rule_parameter_the_guard_does_not_know_is_a_violation"]},
    ),
    (
        "the report-only list is not among the guarded parameters",
        CI,
        'RULE_GUARDED = {*RULE_NOT_HIGHER, *RULE_STAYS_ON, "report_only"}',
        "RULE_GUARDED = {*RULE_NOT_HIGHER, *RULE_STAYS_ON}",
        {G: ["test_every_rule_parameter_in_the_committed_protocol_is_guarded"]},
    ),
    (
        "a blocking rule may be turned off",
        CI,
        "        elif before is not after and not after:",
        "        elif False:",
        {G: ["test_a_blocking_rule_may_be_turned_on_and_never_off"]},
    ),
    (
        "a reference may join the report-only list",
        CI,
        'PROTOCOL_NO_NEW += (("rule", "report_only"),)  # a reference added here stops blocking',
        "PROTOCOL_NO_NEW += ()",
        {G: ["test_a_reference_may_leave_the_report_only_list_and_never_join_it"]},
    ),
    (
        "a floor exception is not an exemption",
        CI,
        '        ("budgets.toml", _exceptions),\n',
        "",
        {
            I: [
                "test_a_floor_exception_added_in_a_change_fails_the_check",
                "test_an_exception_whose_baseline_or_ticket_changed_is_a_new_exception",
            ]
        },
    ),
    (
        "an exception is known by its metric alone",
        CI,
        'return Counter(f"exception {json.dumps(e, sort_keys=True, default=str)}" for e in entries)',
        "return Counter(f\"exception {e.get('metric')}\" for e in entries)",
        {I: ["test_an_exception_whose_baseline_or_ticket_changed_is_a_new_exception"]},
    ),
    (
        "L may be seeded or moved in any change",
        CI,
        '        if after.get("L") != before.get("L"):',
        "        if False:",
        {
            G: [
                "test_a_change_to_l_outside_the_owners_own_commit_is_rejected",
                "test_seeding_l_is_the_owners_own_commit_too",
            ],
            M: ["test_what_promote_writes_is_still_the_owners_to_commit"],
        },
    ),
    # --- scripts/closure.py ----------------------------------------------------------------
    (
        "a post-merge run that is not recorded is never owed",
        CL,
        "            elif touched:",
        "            elif False:",
        {
            G: [
                "test_a_ticket_whose_merge_touched_api_src_still_owes_its_post_merge_run",
                "test_code_merged_in_one_pull_request_is_seen_when_the_manifest_lands_in_another",
                "test_a_change_committed_straight_onto_the_base_is_diffed_as_itself",
                "test_check_file_names_the_manifest_whose_merges_are_diffed",
            ]
        },
    ),
    (
        "a post-merge run is owed whatever was merged",
        CL,
        "touched = None if unmerged else merged_e2e_paths(root, path, passed, base, git)",
        'touched = None if unmerged else ["anything"]',
        {
            G: [
                "test_a_ticket_that_merged_no_product_eval_or_harness_file_closes_without_a_post_merge_run",
                "test_a_change_committed_straight_onto_the_base_is_diffed_as_itself",
            ]
        },
    ),
    (
        "a change to the evals owes no run",
        CL,
        '    "evals/",\n',
        "",
        {G: ["test_what_owes_a_post_merge_run_is_the_product_the_evals_and_the_run_harness"]},
    ),
    (
        "a change to the web build owes no run",
        CL,
        '    "web/",\n',
        "",
        {G: ["test_what_owes_a_post_merge_run_is_the_product_the_evals_and_the_run_harness"]},
    ),
    (
        "a file beside a listed path counts as that path",
        CL,
        'if any(path.startswith(e) if e.endswith("/") else path == e for e in E2E_PATHS)',
        'if any(path.startswith(e.rstrip("/")) for e in E2E_PATHS)',
        {G: ["test_what_owes_a_post_merge_run_is_the_product_the_evals_and_the_run_harness"]},
    ),
    (
        "the merge that brought in a tested head is not looked up",
        CL,
        "    for commit in tested:",
        "    for commit in []:",
        {
            G: [
                "test_code_merged_in_one_pull_request_is_seen_when_the_manifest_lands_in_another",
                "test_a_change_committed_straight_onto_the_base_is_diffed_as_itself",
            ]
        },
    ),
    (
        "the merges that changed the manifest are not looked up",
        CL,
        "    if manifest:",
        "    if False:",
        {G: ["test_check_file_names_the_manifest_whose_merges_are_diffed"]},
    ),
    (
        "a commit made straight onto the base is diffed as the commit after it",
        CL,
        "landed.add(commit if first.stdout.strip() == commit or merge == commit else merge)",
        "landed.add(merge)",
        {G: ["test_a_change_committed_straight_onto_the_base_is_diffed_as_itself"]},
    ),
    (
        "work that is not on the base may close without a run",
        CL,
        't for t in passed if git(root, "merge-base", "--is-ancestor", t, base).returncode',
        "t for t in passed if False",
        {G: ["test_work_that_is_not_on_the_base_cannot_close_without_a_run"]},
    ),
    (
        "a merge git cannot diff counts as having merged nothing",
        CL,
        '        diff = git(root, "diff", "--name-only", f"{commit}^1", commit)\n'
        "        if diff.returncode:\n            return None",
        '        diff = git(root, "diff", "--name-only", f"{commit}^1", commit)\n'
        "        if diff.returncode:\n            continue",
        {G: ["test_a_merge_git_cannot_diff_owes_the_run"]},
    ),
    (
        "a half-recorded post-merge run counts as none recorded",
        CL,
        "        if not e2e and not main_head:",
        "        if not e2e or not main_head:",
        {G: ["test_a_half_recorded_post_merge_run_is_not_waved_through"]},
    ),
    (
        "check_file does not say which manifest it is checking",
        CL,
        "return problems(load(path), path=inside, **kwargs)",
        "return problems(load(path), **kwargs)",
        {G: ["test_check_file_names_the_manifest_whose_merges_are_diffed"]},
    ),
    # --- scripts/check_budgets.py ----------------------------------------------------------
    (
        "a waived run is also reported as excepted",
        CB,
        'excepted = "" if p95 <= limit or waived else _excepted(',
        'excepted = "" if p95 <= limit else _excepted(',
        {B: ["test_a_waived_run_is_reported_as_waived_not_excepted"]},
    ),
    (
        "malformed exceptions are not reported",
        CB,
        "    if problems := metric_compare.exception_problems(budgets):",
        "    if problems := []:",
        {B: ["test_a_malformed_exception_is_itself_a_failure_and_excuses_nothing"]},
    ),
    (
        "an excepted row is printed as waived",
        CB,
        'status = "waive" if check.waived else "excpt"',
        'status = "waive"',
        {B: ["test_main_labels_an_excepted_quality_floor_and_counts_it"]},
    ),
    (
        "a quality floor is never looked up for an exception",
        CB,
        'excepted = _excepted(limit_key, value, budgets) if can else ""',
        'excepted = ""',
        {B: ["test_main_labels_an_excepted_quality_floor_and_counts_it"]},
    ),
]


def new_tests() -> dict[str, set[str]]:
    """Per test file, the test names this branch has and origin/main does not."""
    out = {}
    for path in (M, G, B, I):
        base = subprocess.run(
            ["git", "show", f"origin/main:{path}"], capture_output=True, text=True, encoding="utf-8"
        ).stdout
        out[path] = names(Path(path).read_text(encoding="utf-8")) - names(base)
    return out


def names(text: str) -> set[str]:
    return {line[4:].split("(")[0] for line in text.splitlines() if line.startswith("def test_")}


def pytest(nodes: list[str]) -> tuple[dict[str, tuple[int, int]], str]:
    """({test name: (cases failed, cases run)}, pytest's last line) for one run of `nodes`."""
    done = subprocess.run(
        ["uv", "run", "pytest", *nodes, "-q", "-rA", "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    seen: dict[str, tuple[int, int]] = {}
    for line in done.stdout.splitlines():
        word, _, rest = line.partition(" ")
        if word in ("PASSED", "FAILED", "ERROR") and "::" in rest:
            name = rest.split("::")[1].split("[")[0].split(" ")[0]
            failed, ran = seen.get(name, (0, 0))
            seen[name] = (failed + (word != "PASSED"), ran + 1)
    return seen, (done.stdout.strip().splitlines() or ["(no output)"])[-1]


def main() -> int:
    check_only = "--check" in sys.argv
    bad_anchor = []
    for name, path, old, new, _tests in MUTATIONS:
        found = Path(path).read_text(encoding="utf-8").count(old)
        if found != 1 or old == new:
            bad_anchor.append(f"{name}: found {found} time(s) in {path}")
    for line in bad_anchor:
        print(f"CANNOT APPLY  {line}")
    if bad_anchor or check_only:
        print(f"{len(MUTATIONS)} mutations, {len(bad_anchor)} cannot apply")
        return 1 if bad_anchor else 0
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout
    dirty = subprocess.run(["git", "status", "--short"], capture_output=True, text=True).stdout
    print(f"HEAD {head.strip()}  base origin/main  worktree {'clean' if not dirty else 'DIRTY'}")
    if dirty:
        print(dirty)
        return 1
    _seen, last = pytest([M, G, B, I])
    print(f"BASELINE (nothing reverted) {last}\n")
    good: set[tuple[str, str]] = set()
    bad: list[str] = []
    for name, path, old, new, tests in MUTATIONS:
        file = Path(path)
        original = file.read_bytes()
        nodes = [f"{test_file}::{test}" for test_file, found in tests.items() for test in found]
        try:
            file.write_bytes(original.decode("utf-8").replace(old, new).encode("utf-8"))
            seen, last = pytest(nodes)
        finally:
            file.write_bytes(original)
        print(f"REVERTED: {name}  [{path}]")
        for test_file, found in tests.items():
            for test in found:
                failed, ran = seen.get(test, (0, 0))
                label = "GOOD" if failed else "BAD "
                print(f"  {label}  {test}  ({failed} of {ran} case(s) failed)")
                if failed:
                    good.add((test_file, test))
                else:
                    bad.append(f"{name} :: {test}")
        print(f"        {last}\n")
    left = subprocess.run(["git", "status", "--short"], capture_output=True, text=True).stdout
    uncovered = [
        f"{path}::{test}"
        for path, tests in new_tests().items()
        for test in sorted(tests)
        if (path, test) not in good
    ]
    total = sum(len(found) for *_rest, tests in MUTATIONS for found in tests.values())
    print(f"{len(MUTATIONS)} mutations, {total} test runs: {total - len(bad)} GOOD, {len(bad)} BAD")
    for line in bad:
        print(f"  BAD  {line}")
    print(f"new tests with no GOOD mutation: {len(uncovered)}")
    for line in uncovered:
        print(f"  UNCOVERED  {line}")
    print(f"worktree after the run: {'clean' if not left else 'DIRTY: ' + left}")
    return 1 if bad or uncovered or left else 0


if __name__ == "__main__":
    sys.exit(main())
