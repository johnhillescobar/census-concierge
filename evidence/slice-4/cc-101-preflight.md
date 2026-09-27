# CC-101 pre-flight

Claims checked against the code before implementation started.

| Claim | Command | Result |
| --- | --- | --- |
| `find_state()` in `api/src/geo_list.py:73-86` | `Read api/src/geo_list.py` | Matched exactly; last-match tie-break confirmed as the bug source. |
| `ResolveGeographyTool._resolve` calls `find_state(parent_text)` once, `api/src/geo.py:259-262` | `Read api/src/geo.py` | Matched (`state = find_state(parent_text)` at line 262). |
| Branch selection `sides = legs if len(legs) >= 2 else split_comparison(query)`, `api/src/geo.py:220-221` | `Read api/src/geo.py` | Matched exactly. |
| CC-100 tests `test_bare_unqualified_city_names_resolve_all_places` exists | `grep` in `api/tests/test_ask_loop.py` | Exists verbatim. |
| CC-100 test `test_wildcard_listing_not_treated_as_comparison_list` exists | `grep` across `api/tests/` | Not found verbatim; the actual coverage is `test_split_comparison_ignores_wildcard_and_within_listing_queries` (`api/tests/test_ask_tools.py`), which asserts `split_comparison("all counties in Texas and Louisiana") is None` — the exact repro query. Comment's citation was descriptive, not literal; used the real test name for AC13 tracking. |
| DC/Kansas City/NYC collision tests exist (AC15) | `grep` in `api/tests/test_ask_tools.py` | `test_washington_dc_is_not_washington_state` (~line 1434) already covers DC-vs-Washington and Kansas City. Left `find_state` untouched, so this test is unaffected and re-verified green post-implementation. |
| `budgets.toml` headroom | `uv run python scripts/check_budgets.py` | Pre-change: `api_src_loc` 4076/4100 (24 headroom), `largest file LOC` 409/410 (1 headroom, file was `ask.py`; `geo.py` measured 406/410, 4 headroom). Extremely tight — flagged as a real risk before writing code. |

## Design decision driven by pre-flight

`geo.py`'s 4-line headroom could not absorb a naive per-parent orchestration
function (~15-20 lines). Landed on adding a `parent_override` parameter to
the existing `_resolve()` instead of a new async helper, and moved the
`WILDCARD`/`WITHIN` regex constants from `geo.py` to `geo_list.py` (net
line-neutral across the pool, but relieves `geo.py`'s own file cap). Final
measured state: `api_src_loc` 4099/4100, `geo.py` 410/410 — both at their
exact ceiling, zero headroom for the fix phase if Gate 2 finds something
that needs new lines in `geo.py` specifically.
