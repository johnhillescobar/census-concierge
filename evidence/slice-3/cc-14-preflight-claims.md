# CC-14 pre-flight — claims vs measured

Raw command output: `evidence/slice-3/cc-14-preflight.txt`.

Settled on `origin/main` @ `8fe48f2` (CC-73 merged). Jira `CC-14` To Do → In Progress, parent CC-4 (agent harness). Slice 3 is the current product slice; this ticket is harness, not a PLAN.md series checkbox.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| Invariant checks name the forbidden patterns they enforce | `scripts/check_invariants.py` prints `ok    no violations` on a clean tree; functions exist for agent frameworks, sqlite, contextvars, ticket-named tests, prompt imports, and `--base` budget weakening | **Holds as a gap.** Failures name a pattern; success does not. Budget increases, blocking clarification, and `*_manager`/`_orchestrator`/`_factory`/`_policy`/`_strategy`/`_service` are not checks. |
| Census API `key` is redacted from user-visible logs and artifacts | `CensusURL` strips `key`; `redact_text`; `run_demo.leaks_key` refuses to write `evidence/latest.json`; web `redactCensusUrl`; no `[?&]key=` in `evidence/*.json` | **Holds as runtime, gap as invariant.** A leaked key in committed JSON is not a `check_invariants` failure. |
| Missing runtime secrets produce an explicit failure rather than silent degradation | `run_demo` exits 2 if `OPENAI_API_KEY`/`CENSUS_API_KEY` unset. `rerank.py` uses `os.environ["GEMINI_API_KEY"]`. `ask.py` `default_tools` uses `os.environ.get("CENSUS_API_KEY", "")`; `CensusURL.with_key("")` omits the key and Census may still 200 | **Holds as a gap.** Empty Census key is silent degradation. `ask.py` is 399/400 LOC — fail-closed must not grow the file without a matching cut. |
| The checks run automatically in the normal validation path | `make check` → `invariants`; `.pre-commit-config.yaml` hook; `.github/workflows/check.yml` with `fetch-depth: 0` and `--base` | **Holds.** Do not add a second runner. |

## Decision

Keep `check_invariants.py` as the one checker. Print every named pattern on success (same shape as `check_budgets.py`). Add greps for forbidden module suffixes, clarification filenames, empty `os.environ.get` defaults on the three API keys, and `[?&]key=` (not `REDACTED`) in `evidence/**/*.json`.

In `default_tools`, fail closed on a missing/empty `CENSUS_API_KEY` *before* loading the index. Same for `OPENAI_API_KEY` in `_openai_complete`. Raise `ValueError` so `run_ask`'s `except RuntimeError` cannot turn a missing key into HTTP 200 prose. Compress `dispatch`'s consecutive-failure block so `ask.py` stays ≤400 LOC.

## Out of this ticket

Slice 3 series guards still open in PLAN. New tool, route, graph node. Raising any budget. Scanning gate `*.txt` transcripts (they contain test `key=secret` fixtures). Changing `run_demo.leaks_key` (already correct).
