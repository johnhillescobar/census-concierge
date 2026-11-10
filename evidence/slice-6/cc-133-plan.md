# CC-133 plan (the one plan file for this story)

Branch `cc-133/instrument`, cut from `main` 57f7533 on 2026-11-09. Yardstick: an instrument, not a feature.
**No runtime change, no product-gain claim, no budget change.** Owner direction: Jira CC-133 (2026-11-08
refinement) and PLAN "Instrument first".

## Pre-flight: every claim in the ticket, run against the repo

| Claim | Settled by | Result |
| --- | --- | --- |
| `jira_transition.py` has Done paths | read the file | **Two**: `--done` and `--transition Done` (`main`, lines 126-157). The gate must cover both. |
| Existing gate scripts to integrate into | `ls scripts` | `gate.sh`, `gate.ps1` (print a handoff only), `check_invariants.py`, `check_budgets.py`. |
| Cases carry independent family IDs | `evals/golden_questions.toml` | **False.** 4 core, 48 long_tail, 18 trap; no `family` field. Default below. |
| "No golden uses a list" (Jira comment 10831) | `grep 'expect_geo_level *= *\['` | True, 0 hits. |
| Scorer exists and is hashable | `scripts/run_demo.py` | `is_answered`, `level_problems`, `census_urls`, `fetched_level`, `http_ok`, `_WARNING_WITHOUT_FETCH`. |
| CC-132 already lost the instrument scope | Jira CC-132 | True ("Early instrumentation moved to CC-133"). Nothing to move. |
| Main is green so the story starts clean | `check_budgets.py` | **False.** Red before any change: doc_lines 1822 > 1820, p95 25.472 > 20, answered_rate 0.683 < 0.700. |
| CC-114 closeout supplies the anchor | Jira link, PLAN line 34 | CC-114 is Done (merged 69d7364, owner close with floors unmet). |
| PLAN says rollback comes first | PLAN lines 41-42, 46 | **Conflicts with the above.** The rebuild already merged; "post-rollback, pre-fix anchor" cannot be taken now. |
| Execution is isolated from question wording | grep `record.question`, `re.` in api/src | **False today.** `guards.py`, `ask.py`, `finish.py`, `vintages.py` read `record.question`; `geo.py` scans `query` (`detect_level`, `split_comparison`, `_nation`). The harness will expose this; it does not fix it (AC4). |

## Decisions (tagged; a default is never an owner decision)

| # | Decision | Tag |
| --- | --- | --- |
| D1 | **A = main 69d7364** (CC-114 post-merge E2E, `evidence/slice-6/cc-114/e2e-post/`). **A0 = 4b24f77** (CC-114's pre-fix anchor, `.../anchor/`). Both registered as `legacy-unfrozen-protocol`, floors unmet recorded as blockers, never as acceptable losses. PLAN lines 41-42 and 46 are stale against the merge; I do not edit them without the owner. | default; **owner to confirm** |
| D2 | Family = question id until the owner assigns families. Trial rate = answered trials / trials. Case rate = share of cases answered in **all** repeats. Both reported, both gated. | default |
| D3 | Paired comparison: bootstrap over families (10,000 resamples, fixed seed), two-sided 95% percentile interval. Observed decrease = FAIL. Point >= 0 with lower bound < -0.02 = INCONCLUSIVE. Fewer than 30 families = INCONCLUSIVE. Any scorer, cohort or protocol hash difference without a bridge = FAIL. | default |
| D4 | Stopping: fixed planned blocks (repeat 3 x every family), order-balanced B,P,P,B. No optional stopping, no rerun-until-green; every run is appended to the ledger. | default |
| D5 | Closure manifest `evidence/closure/<KEY>.toml`. Required IDs come from the ticket's exact `AC<n>.` / `TC<n>.` identifiers at Done time. A ticket with none has none required. | default |
| D6 | The isolation harness is pytest in `api/tests`. Failures that exist today are `xfail(strict=True)` naming the owning ticket, so a fix forces the marker out. | default |
| D7 | Docs edits are net-negative (main is 2 lines over). `budgets.toml` untouched. | default |
| D8 | **No oracle review.** The owner will not sign one (2026-11-10). Cohort hashes cover the expectations; a changed expectation moves its hash and needs a bridge. Removed in aa1feb1. | owner |

## AC / TC matrix (IDs fixed before implementation)

| ID | Expected | Command / test | Status |
| --- | --- | --- | --- |
| AC1 | Protocol, cohorts, denominators, scorer and config hashes frozen before results | `metric_compare.py freeze --check`; `test_metric_protocol.py` | NOT RUN |
| AC2 | B/P/A/L, ratchets, repeat-3 case and trial metrics, family intervals, contract and p95, every block retained | `metric_compare.py compare`; `test_metric_compare.py` | NOT RUN |
| AC3 | Post-CC-114 anchor registered with hashes; failing metrics listed as blockers; scorer bridge for changed code | `metric_compare.py register`; bridge test | NOT RUN |
| AC4 | Isolation harness: fixed intent/changed wording, changed intent/same wording, repair path, keyword mutants caught | `test_execution_isolation.py` | NOT RUN |
| AC5 | Manifest gate in `jira_transition.py` (both Done paths), `check_invariants.py`, gate handoff | `test_closure_gate.py` | NOT RUN |
| AC6 | Own AC/TC PASS with evidence; rejects an incomplete closure, accepts a valid one; no budget change; applicable E2E | `closure.py check evidence/closure/CC-133.toml` | NOT RUN |
| TC1 | One cohort up, another down: rejected | compare test | NOT RUN |
| TC2 | Sequential small decreases cannot reset A or a floor | ratchet test | NOT RUN |
| TC3 | Scorer, denominator or hash change cannot read as code gain | compare test | NOT RUN |
| TC4 | Same intent, different prose: identical execution; prohibited access caught | isolation tests + mutants | NOT RUN |
| TC5 | Missing/NOT RUN/stale/no post-merge blocks Done | closure tests | NOT RUN |
| TC6 | Small sample inconclusive; repeats not independent | compare tests | NOT RUN |
| TC7 | Faster failures, dropped rows, blanket refusal, outage filtering cannot pass | compare tests | NOT RUN |
| INH | `check_budgets` and `check_invariants --base origin/main` no worse than main; regex delta 0; p95 and answered_rate reported against A | `make check`; E2E | NOT RUN |

## Outward writes (listed before they happen)

- repo: branch `cc-133/instrument`, commits, `evidence/slice-6/cc-133/`.
- Jira CC-133: one pre-flight comment (this table's findings and D1-D8), requested by the owner. Later: the close card.
- PR: opened for the owner to merge. I do not merge, waive, or flip any golden.

---

## Status at 93d8692 (2026-11-10) - supersedes the NOT RUN column above

The matrix now lives in `evidence/closure/CC-133.toml`; `uv run python scripts/closure.py check evidence/closure/CC-133.toml --pre-merge` exits 1 by design (every row UNKNOWN or NOT RUN).
Evidence: `evidence/slice-6/cc-133/` (gate1.txt, gate1-fixes.txt, gate1-newtests.txt, gate1-rerun-fixes.txt, gate2.txt, gate2-r2.txt, e2e-pre/).
Corrections to the pre-flight: AC1 named a test_metric_protocol.py that was never written (coverage is in test_metric_compare.py).
D5 is stricter than planned: a Story or Bug with no recognised AC/TC ids is refused, not waved through. E2E ran at 71fa8d5 and predates the has_moe fix (93d8692).
Open for the owner: strict no-decrease tolerance, trap/core cohort size, A0-to-A bridge, a third review of the fix delta.

## Status at 18a1bce (2026-11-10) - supersedes the status above

Gate 2 ran three times; the third review (gate2-r3.txt) found closure type-strictness gaps and a forgeable L proof, all fixed and mutation-checked (31 of 31, gate1-third-review*.txt). The final fix delta has no independent cold review. E2E still predates the has_moe fix.
Reference L now moves only with a ledger PASS record that names the same run, file hash and head; bridges are owner-only.
