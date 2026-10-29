# CC-121 Gate 2 re-run: what was found and what was done (2026-10-18)

Raw review: `cc-121-gate2-rerun.txt` (cold subagent, `/code-review` pass then `docs/playbooks/review-pr.md` pass). Earlier review of an older revision: `cc-121-gate2.txt`.

| # | Severity | Finding | Disposition |
|---|---|---|---|
| 1 | HIGH | Labels, table title and universe were looked up once for the newest year and applied to every year's rows, so a 2019 figure could carry "(in 2024 dollars)". The vintage planner (`same_definition` + `strip_vintage`) deliberately keeps years whose title differs only by a dollar year, so the case is reachable. | Fixed. Rendering moved to `api/src/figures.py` (`fetch.py` was at its 410-line cap); each figure takes its own year's label, and the closing line is per year (prefixed with its years only when the table changed). Three tests added; four mutants (newest-year labels, newest-year closing line, never prefix, always prefix) all fail their test. |
| 2 | MEDIUM | `finish_tools()` runs `fetch_data` after the model has stopped and discards the tool text, so on that path the model never sees the figures. | Not fixable without an end-of-request model call, which the owner ruled out. Documented as a known gap in `docs/ask-path.md`. The prompt tells the model to state only fetched figures, and the offline judge scores these answers too. |
| 3 | MEDIUM | `review-pr.md:63-64` ("the model must never handle the value") conflicts with the design. | Owner decision, open. The rule was not edited. |
| 4 | MEDIUM | Instrument: the judge sees every fetched row while the model saw 20 figures (rate is a lower bound); labels were also built from the newest year only; `collect` overwrote an existing label's output; the default judge equalled the default answer model. | Labels now per year; `collect` refuses an existing `--label`; label guard catches any failure; default judge is gpt-4.1. The lower-bound caveat is stated in `cc-121-results.md`. The arms are re-collected with the corrected instrument. |
| 5 | LOW | The test fakes returned the same label for every year, so mutating `max` to `min` survived. | Fixed by the per-year tests in finding 1. |
| 6 | LOW | The 20-figure cap is place-major, so a long listing hides later places. | Within the owner's "first 20" decision; the "k of n shown" line says so. Follow-up: CC-122. |
| 7 | LOW | `metadata.variables` is uncached (about 0.1 s per year looked up). | Now one lookup per distinct year among the shown figures, off the event loop. Cost is checked by `demo.p95_latency_seconds`. The unit tests no longer read `data/raw` (autouse fixture), which also removed a timing flake in `test_fetch_years.py`. |
| 8 | LOW | `table_facts` was called when the fetch failed. | Fixed: no figures, no lookups when there are no rows. |
| 9 | LOW | A margin-of-error sentinel renders as "not published". | Matches `docs/requirements.md:11`; no change. |
| 10 | NIT | Module-level lists in the tests. | Left; they are reset by the autouse fixture. |
