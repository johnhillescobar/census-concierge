# CC-118 plan — Census `get` variable limit

Branch `cc-118/variable-limit`, cut from `origin/main` 261c18f in an isolated
worktree. Jira CC-118 is the scope and status source. Prerequisite CC-133 is
Done; CC-118 blocks CC-82.

## Yardstick

`build_url` rejects an explicit `get` list above Census's 50-variable cap
before any HTTP request, while preserving the redacted over-limit URL and a
visible deterministic notice. It counts the actual unique outgoing columns:
`NAME`, `GEO_ID`, each estimate, and each paired margin. CC-82 owns `group()`
and request splitting.

## Pre-flight

| Claim | Command / inspection | Result |
| --- | --- | --- |
| The live cap counts the `get` list at 50 | Authenticated ACS5 2023 requests for B15003, state 06 | 24 E/M pairs + `NAME,GEO_ID` = 50 returned HTTP 200; 25 pairs = 52 returned HTTP 400, `error: 'get' is limited to 50 variables` |
| Current `build_url` has no cap guard | `api/src/tools.py`, `BuildUrlTool._arun` | True: it builds `get_cols` and returns `ok=True` without checking its length |
| E/M inputs are deduplicated | `pair_margins` and normalization in `BuildUrlTool._arun` | True: explicit M variables add their E once; `pair_margins` is idempotent |
| Failed builds normally carry no URL | `_build_fail`, `ask._absorb` | True; CC-118 must preserve only this inspectable rejected URL without making it fetchable |
| A failed URL could be retried by finish | `finish_tools` build/fetch conditions | True; structured over-limit state must prevent an automatic fallback build while allowing an explicit smaller model retry |
| Baseline URL-tool tests pass | `uv run pytest api/tests/test_ask_tools.py -q` | 129 passed |
| Budget headroom exists | `uv run python scripts/check_budgets.py` | False: API LOC is 4890/4890 and `ask.py` 408/410; implementation must be net-nonpositive. Inherited answered rate is 0.683 < 0.700; the old p95 waiver does not cover CC-118 |

The first unauthenticated live probe returned an HTTP 200 HTML “Missing Key”
page, not Census data. The authenticated JSON probe above is the valid result.

## AC / TC matrix

| ID | Expected outcome | Verification | Initial status |
| --- | --- | --- | --- |
| AC1 | At most 50 unique outgoing `get` columns succeeds; more than 50 returns `ok=False` before HTTP | Boundary tool tests and live 24/25 test | NOT RUN |
| AC2 | Failure detail names actual count, limit 50, and maximum 24 estimates | Tool and ask-loop tests | NOT RUN |
| AC3 | Rejected result preserves the full redacted URL and displays a deterministic warning notice | Tool and assembled-response tests | NOT RUN |
| AC4 | No HTTP request is attempted for the rejected URL; an explicit smaller retry remains possible | Real dispatch/fetch/finish test with counted HTTP fake | NOT RUN |
| AC5 | Existing budgets are not raised; ordinary requests and CC-100 list behavior remain unchanged | Budgets, focused/full tests, invariants | NOT RUN |
| TC1 | 24 estimates produce 50 `get` columns and succeed; live request returns rows | Unit plus authenticated live boundary | NOT RUN |
| TC2 | Twelve E variables plus their twelve explicit M variables count as 26 unique outgoing columns, not 50 requested entries | Deduplication test | NOT RUN |
| TC3 | A different table with 25 estimates fails at build time | Parameterized tool test | NOT RUN |
| TC4 | One estimate and existing multi-geography/list paths are unchanged | Existing URL and CC-100 suites | NOT RUN |
| TC5 | Thirty estimates fail, expose the URL/notice, and a later explicit 24-estimate retry can fetch | Ask-loop integration test | NOT RUN |

All deterministic rows must pass 100%. Every new test is mutation-checked by
removing or bypassing the cap behavior and observing the focused failure.

## Default implementation decisions

- Add structured `over_limit` state to `BuildUrlResult`; do not infer failure
  type from detail text.
- Keep the rejected URL in response history, never in the executable
  `record.url` slot.
- Append the trusted limit notice after model-figure checking so its required
  counts are not mistaken for model-authored figures.
- Do not add a warning code: the warning catalog defines none for this case.
- Reduce existing equivalent code so the change stays within current budgets.

## Outward writes

- Repository: this plan, implementation/tests, closure manifest, phase evidence,
  commits, and a CC-118 branch/PR.
- Jira: move CC-118 to In Progress with the corrected authenticated pre-flight;
  later attach gate/scoreboard evidence. Do not mark Done before owner merge and
  post-merge E2E.
- No budget, sealed-set, or owner-only merge writes.
