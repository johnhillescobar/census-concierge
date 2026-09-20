# Slice 3 demo misses — why they happen, what tickets own them

Dated **2026-09-18**. Written so a later session can `@` this file instead of
reloading the chat. Not prescriptive: do not copy into `CLAUDE.md`, `PLAN.md`,
or rules. Those load every turn; this does not.

Confluence was considered and skipped. The Atlassian MCP in this workspace is
not a Confluence store, and a wiki copy would drift from git. Jira already has
the AC; this file is the *why*.

## When to open this

- Interpreting leftover `make demo` misses after slice 3 closed.
- Tempted to add a new epic, a new floor, or cousin-table AC onto those tickets.

Do **not** open it to implement a random long-tail miss.

## Pinned run

CC-73 post-merge E2E, `--repeat 3`.

| | |
|---|---|
| transcript | `evidence/slice-3/cc-73-e2e-post.txt` (do not Read it)
| scoreboard | `evidence/latest.json` from that run |
| `retrieval_at_10` | 0.90 (floor 0.90) |
| `selector_at_1` | 0.85 (floor 0.70) |
| `synthetic_alignment` | 0.544 (floor 0.50) |
| `answered_rate` | 0.778 long_tail (floor 0.70) |
| `demo.p95` | 20.066s (ceiling 20; over-ceiling, not promoted) |
| `overall_answered_rate` | 0.712 (includes traps; **not** gated) |
| `prompt_hash` / `index_hash` | `45b4e3d20ca0` / `377cd59fe62a` |

`demo.misses` (44 rows / 3 repeats): q04, q05, q08, q10, q11, q17, q18, q20,
q21, q28, q34, q36, q39, t01, t03, t04, t06, t08.

PLAN STATUS at the time: *Demo still `is_slice1()`*. That filter is in
`scripts/run_demo.py`: holdout out, **`q23` dropped by name**, traps **`t09`–`t18`
dropped**. So this miss list is the slice-1 subset. It does **not** measure
CC-74/75/76.

CC-74 post-merge E2E (`evidence/slice-3/cc-74-e2e-post.txt`, `--repeat 3`):
`answered_rate` 0.786, `p95` 19.619s, `selector_at_1` 0.875. `demo.misses`:
q04, q10, q11, q17, q18, q20, q21, q24, q34, q36, q39, q41, t01, t03, t04,
t06, t08. `t13` is still excluded by `is_slice1()`. The failure modes below
still apply; they are not a reason to reopen CC-74.

CC-75 post-merge E2E (`evidence/slice-3/cc-75-e2e-post.txt`, `--repeat 3`, n=171):
`answered_rate` 0.769, `p95` 14.737s, `selector_at_1` 0.875. `demo.misses`:
q04, q05, q08, q10, q11, q17, q18, q20, q21, q28, q34, q37, q39, q41, t03, t04,
t06, t07, t08, t10, t11, t12, t13. `t09` and `t14` are not in the miss list.
`t10`–`t13` are now in the suite and miss on missing warnings; they are not a
reason to reopen CC-75.

CC-76 post-merge E2E (`evidence/slice-3/cc-76-e2e-post.txt`, `--repeat 3`, n=186):
`answered_rate` 0.825, `p95` 17.116s, `selector_at_1` 0.875. `demo.misses`:
q10, q11, q15, q17, q18, q20, q34, q39, q41, t07, t11, t14. `q23` and `t15`–`t18`
are not in the miss list. `t14` missing `variable_not_in_vintage` is not a reason
to reopen CC-76. Slice 3 closed. `retrieval_at_1_holdout` 0.625 (n=8).

CC-92 post-merge E2E (`evidence/slice-3/cc-92-e2e-post.txt`, `--repeat 3`, n=186):
`answered_rate` 0.842, `p95` 17.585s, `selector_at_1` 0.875. `demo.misses`:
q10, q11, q17, q18, q20, q34, q39, q41. `t14` is not in the miss list.

## What “answered” means

HTTP 200 is not answered. `scripts/run_demo.py` `is_answered()` requires:

- expected warning present, if the golden row names one
- a Census URL, unless the warning is `ambiguous_place` or `geography_not_nested`
- expected table, URL, and rows, if the golden row names a table

DESIGN: guards warn **and ship**. The harness follows that. A correct warning
with an empty `urls[]` is a miss.

## Three failure modes (machinery exists; the trial still misses)

### 1. Wrong cousin table (most of the long tail)

Selector `@1` is 0.85, so about one in six long-tail questions is already the
wrong table. The agent can also override a good hit. Examples from this run:

- `q10` expected `C16001`, fetched `B16001`, geography Queens PA not Queens NY
- `q11` expected commute distribution `B08303` at the Atlanta CBSA; fetched
  aggregate `B08136` for Atlanta the place
- `t08` asked for income *distribution* `B19001`; got `B19101` or `B19082`

Later slices do not teach the index these cousins. **Out of scope for CC-75/76.**
Already gated by `selector_at_1` and long-tail `answered_rate`. User-facing fix
is slice 4 (alternatives panel), not a new epic.

### 2. Guard fired; loop did not ship a fetch

- `t01` fired `overlapping_vintage` (and sometimes `geography_unsupported`) but
  `table_id` / URL were empty
- `t06` fired `universe_mismatch`, miss detail `empty url`
- `q04` often fired `ambiguous_place` then never picked `B17001` (q04 is core,
  so the warning alone does not count)

### 3. Guard never saw the facts it needs

`moe_not_significant` requires compare-words **and** ≥2 rows with E and M.
`t03` (“tract 1201 vs 1305”, no state/county) often has 0 rows, so the miss is
`missing warning moe_not_significant` even though the function exists.

`t04` (Wyoming block groups): one repeat substituted `for=state:56` with no
`geography_unsupported`; another warned and shipped no URL. Silent repair is
the trap. Guard is already slice 1; do not reopen it inside CC-74/75/76.

## What remaining tickets own

Closed under epic [CC-2](https://johnhillescobar.atlassian.net/browse/CC-2):

| ticket | owns | live questions |
|---|---|---|
| [CC-75](https://johnhillescobar.atlassian.net/browse/CC-75) Done | `variable_not_in_vintage`, `measure_unavailable`, warn-and-ship on vintage/measure traps | `t09`, `t14` not in CC-75 post-merge misses; `t14` missed on CC-76 post-merge |
| [CC-76](https://johnhillescobar.atlassian.net/browse/CC-76) Done | `MOE_diff`, shared-sample caveat, two-leg fetch before significance | `q23`, `t15`–`t18` not in post-merge misses |

Closed under epic [CC-91](https://johnhillescobar.atlassian.net/browse/CC-91):

| ticket | owns | live questions |
|---|---|---|
| [CC-92](https://johnhillescobar.atlassian.net/browse/CC-92) Done | persist vintage compatibility on the fetch artifact; `variable_not_in_vintage` from `omission_reasons` | `t14` not in post-merge misses |

AC added **2026-09-18** (on the tickets, not here):

**CC-75**

- `make demo` includes `t09` and `t14`. Stop dropping `t09`–`t14` in
  `is_slice1()`. Holdout, `q23`, and `t15`–`t18` stay excluded until CC-76.
  Quote those IDs from `evidence/latest.json`. Pytest is not done.
- When `measure_unavailable` / `variable_not_in_vintage` / `overlapping_vintage`
  fires, `urls[]` still ships. `t09` / `t14` / `t01` with the right warning and
  an empty URL are misses of that ticket.

**CC-76**

- `make demo` includes `q23` and `t15`–`t18`. After this ticket, `is_slice1()`
  is gone except holdout.
- `moe_not_significant` / `MOE_diff` run only after two comparable fetched legs.
  `t03`: fetch both tracts, or fail closed with `geography_unsupported` plus
  candidates/URLs — never score a missing warning against 0 rows.
- `t06` `universe_mismatch` with an empty URL is a miss of that ticket.

Do **not** add `q05` / `q10` / `q11` / `t08` to either ticket.

## What not to do

- **No new epic** for “fix the scoreboard.” Unbounded quality work.
- **No new floor** and do not gate trap rate. Raising `answered_rate_min` or
  adding a trap floor is a human `budgets.toml` commit with a written reason.
- **Do not** treat the CC-73 miss list as CC-75/76 scope. Those IDs were not in
  the demo filter those tickets will turn on.
- The missing *metric* for remaining slice 3 work is already named: drop
  `is_slice1()` for the questions each ticket owns, then quote the scoreboard.

## Related paths

```
scripts/run_demo.py          is_slice1, is_answered, _WARNING_WITHOUT_FETCH
api/src/guards.py            overlapping_vintage, moe_not_significant, …
evals/golden_questions.toml  t01, t03, t09, t14, q23, t15–t18
```
