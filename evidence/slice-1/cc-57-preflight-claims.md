# CC-57 pre-flight — claims vs measured

Raw command output: `evidence/slice-1/cc-57-preflight.txt`.
Settled on `feat/cc-54-search-select` @ `93fee04`.
Branch `feat/cc-57-default-total` targets `feat/cc-54-search-select`, not `main`.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| Empty `variables` currently means every E | `BuildUrlInput` description line 51; `_arun` lines 250–251 expand to every suffix | **Holds.** This is the defect. |
| `pair_margins()` already exists and is idempotent | `def pair_margins` line 125 | **Holds.** After defaulting to `{table}_001E` it will add `001M`. Do not rewrite pairing. |
| Availability stores estimate suffixes only | `metadata.variables` docstring + `endswith("E")` | **Holds.** Empty expansion of 26 E cells becomes 52 columns after pairing, past the Census `get=` cap of 50. |
| Census `get=` cap is 50 variables | Census API User Guide query limits | **Holds.** `group()` exists but is out of scope: change only the existing URL path. |
| If `001E` is absent, fail with the existing typed result | missing-variable branch already returns `ok=False`, empty URL, `variables not in {dataset} {year}` | **Holds.** Default to `[f"{table_id}_001E"]` and let that path fire. Do not fall back to every cell. |
| Explicit non-empty lists keep current behaviour | same normalize / missing / `pair_margins` loop | **Holds as a constraint.** Touch only the empty-list default. |
| `answered_rate` is long_tail-only | `summarize()` `_rate(long_tail)` | **Holds.** `overall_answered_rate` is absent and must be added beside it, not as a replacement. |
| Do not touch `api/src/retrieval/` | `search()` / `choose()` exist; index_hash `377cd59fe62a` | **Holds as a constraint.** |
| No new tool, route, dependency, model, or budget | four `BaseTool`s; `tools.py` under the 400-line cap | **Holds as a constraint.** |

## Decision

After `table_facts` succeeds, `variables=[]` becomes exactly `[f"{table_id}_001E"]`. Existing validation and `pair_margins()` stay. Empty-list tests use a synthetic 26-estimate table, not a golden-set ID.
