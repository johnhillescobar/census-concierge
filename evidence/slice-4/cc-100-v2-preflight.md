# CC-100 v2 pre-flight — bare unqualified place names (AC8-AC12 redesign)

PR #86 (merged, `f9819dd`) shipped AC1-AC7. Ticket reopened: reporter's post-merge
manual test found bare unqualified comparisons ("Compare the population of
Chicago, Los Angeles and New York City since 2017.") still drop every place but
one, because `geo.py`'s `split_comparison()` list-detection anchors clause
boundaries on `_STATE_END` (state-name/DC tokens); zero anchors -> `None` -> both
call sites (`geo.py`'s merge path, `finish.py`'s `_wrong_comparison`) read that as
"not a comparison at all". AC8/AC9 retire that regex approach outright and mandate
a structured `resolve_geography` input the model fills in itself.

## Claims checked before writing code

| Claim | Command | Result |
| --- | --- | --- |
| `split_comparison`, `_STATE_END`, `_LIST_SEP`, `_ALT`, `_DC_NAMES` exist in `api/src/geo.py` | `grep -n` | confirmed, lines 58-66, 156-175 |
| `ResolveGeographyInput` has no `places` field today | read `api/src/tools.py:37-45` | confirmed: `query`, `level`, `dataset`, `vintage` only |
| `finish.py`'s `_wrong_comparison` calls `split_comparison(question)` on raw question text | read `api/src/finish.py:65-70` | confirmed |
| AC3/AC4/AC5 (answer-leak fix, retry-gate fix) already shipped, unaffected by this redesign | read `api/src/ask.py:443-444`, `api/src/finish.py:140-141` | confirmed: `re.match(r"^[a-z_]+ failed twice$", answer)` fallback and `fetch_failed = record.fetch is not None and not record.fetch.ok` both present on `main` already |
| `find_state("Chicago, IL")` / `place_token` already handle a bare "City, ST" USPS-abbreviated string with no full state name | `uv run python -c "from src.geo_list import find_state, place_token; ..."` | confirmed: resolves `illinois`/`06`/`36` correctly for Chicago/LA/NYC — **no `geo_list.py` change needed**, the USPS-comma path (`geo_list.py:76-78`) already exists |
| `fetch_data` already fetches one row per resolved geography via `record.geographies[:compare_count]` | read `api/src/ask.py:365-369`, `api/src/fetch.py:341` | confirmed — AC11 (table completeness) is a consequence of the core fix, not a separate mechanism |
| Current budget headroom | `uv run python scripts/check_budgets.py` | `api_src_loc 4041/4100` (59 headroom), `largest file LOC 409/410` (1 headroom — `geo.py`) — the state-anchor removal must free at least as many lines in `geo.py` as the `places` plumbing adds, or the file-cap trips |
| Existing tests exercising the retired mechanism | `grep -rn "split_comparison\|_wrong_comparison\|compare_count"  api/tests` | `test_ask_tools.py` has 3 tests (`..._splits_an_and_joined_list_by_state`, `..._keeps_a_state_name_inside_a_place_together`, `..._splits_a_bare_state_versus_state_list`) that assert the retired list-anchor behavior directly — these test the mechanism being retired, not a still-valid contract, so they are removed, not adapted |

## Design (AC8/AC9)

- `ResolveGeographyInput` gains `places: list[str] | None` — each entry already
  canonicalized by the model ("Chicago, IL"), one call resolves all legs. `query`
  becomes optional (default `""`) since a `places` call doesn't need it.
- `split_comparison()` keeps ONLY the `versus` / `compare to` two-way keyword
  split (a literal-keyword split, not prose-boundary inference — AC6's
  regression guard names these explicitly and they are unaffected). The
  `_STATE_END`-anchored comma/"and"-list splitter is deleted outright, along
  with `_ALT`, `_DC_NAMES`, `_END`, `_STATE_END`, `_LIST_SEP`.
- `ResolveGeographyTool._arun` treats `places` (len >= 2) exactly as the old
  `sides` list was treated — same concurrent-resolve-and-merge code, just fed
  from the model's list instead of a regex split of `query`.
- `finish.py`'s repair path is deterministic, no-LLM code; per AC9 it may not
  do prose-boundary inference either. It keeps working for versus/compare-to
  (still text-detectable via a literal keyword) and, per the correction below,
  for sequential single-leg calls (via mechanical call-count bookkeeping, not
  text). It correctly does NOT attempt to repair a bare/list comparison the
  model resolved in one single-string `query` call that came up short — that
  class needs the model to retry inside the normal 8-turn loop with a
  corrected `places` call; a deterministic fallback cannot manufacture
  segmentation from one opaque string without reintroducing the retired
  regex. Deliberate scope boundary, not an oversight.
- `prompts.py`: add an explicit instruction to call `resolve_geography` once
  with `places` for any 2+ way comparison, canonicalizing each place itself
  (state inferred from world knowledge) regardless of whether the user's
  question named one. Budget: `system_prompt_tokens` 251/1200 today, plenty of
  room.
- `contract.py`'s deterministic chart-title fallback (`take_chart`, used when
  the model's own turn supplies no chart JSON) currently titles a multi-geography
  bar/line-with-geography-series chart with only the table_id — that is a
  "generic" title under AC10. Fix: when `series_by`/`x` is "geography" and
  `len(geos) > 1`, include the resolved geography names in the fallback title.
  This is our own deterministic string, not LLM prose — CLAUDE.md's "never
  assert on LLM prose" rule does not apply to it.

## Correction found during implementation

The claim above ("`finish.py` is unchanged") was wrong. Running the full suite
after the `geo.py`/`tools.py` edit broke
`test_sequential_single_place_calls_are_repaired_by_finish_tools` — an
existing, currently-passing regression test for the *original* CC-100 bug
report shape (the model resolves each named place with its own sequential
`resolve_geography` call instead of one compound call). The old repair path
recovered from that by re-running the deterministic split on the *original
full question text*; retiring that splitter removes the only thing that made
the repair possible.

Fix, still with no prose-boundary inference: `ExecutionRecord` gains
`geo_queries: list[str]`, appended to in `_absorb` every time a plain
single-place `query` call resolves legally (cleared on a `places`/comparison/
wildcard call). `finish.py`'s `_wrong_comparison` and its repair call now use
`len(record.geo_queries) >= 2` — a literal count of *how many separate calls
the model already made*, not a re-derivation of "how many places the
sentence names" — to detect and replay those legs as one `places` call. This
is mechanical bookkeeping of what already happened, not the retired regex,
and it is a strict improvement: it now heals sequential bare-name legs too
(the original mechanism only worked because the full sentence happened to
carry state anchors).

Also found empirically: `find_state`/`place_token` treat "New York, NY" as
the *state* (the city and state share a name — the same class of collision
`token_is_dc` exists for Washington/DC), so the AC8 test uses "New York City,
NY" — the name form a model echoing the question's own wording would
naturally produce. Not a code change; noted for the reporter's manual list.

## What is explicitly NOT changed

- `geo_list.py` (`find_state`, `place_token`) — already handles "City, ST".
- `finish.py` — see above.
- `ask.py`'s `_absorb`/`dispatch` — the resolve_geography *output* schema
  (`ResolveGeographyResult`) is unchanged; only the *input* schema gains a field.
- No budget in `budgets.toml` is raised. `geo.py`'s net LOC should go down
  (state-anchor block removed) even after adding `places` handling.

Plan: `.claude/plans/purrfect-roaming-bonbon.md` (superseded — see ticket AC8-AC12).
Branch: `fix/cc-100-bare-place-names`, off `main` at `f9819dd` (PR #86 merged).
