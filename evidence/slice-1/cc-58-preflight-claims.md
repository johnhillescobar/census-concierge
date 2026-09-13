# CC-58 pre-flight — claims vs measured

Raw command output: `evidence/slice-1/cc-58-preflight.txt`.
Predecessor: CC-57 on `feat/cc-54-search-select` @ `d516bd3` (PR #20 merged).

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| `list_census_names` GET is `NAME,GEO_ID` only | `api/src/geo.py` `get=NAME,GEO_ID` | **Holds as a gap.** Must add `B01003_001E` on the same request and keep it as string `population`. Exclude that column from `in=` parents or the clause becomes `state:41 B01003_001E:641165`. |
| Census listing accepts `NAME,GEO_ID,B01003_001E` | live ACS5 2024 `httpx` 200 | **Holds.** Portland city, Oregon `641165` / Maine `68854`; Cook IL `5182090` / GA `17532` / MN `5635`; Springfield city, Missouri `169954`. Place NAME carries LSAD (`city` / `CDP`). |
| `_absorb` sets `geography` only when `len(matches)==1` | `ask.py` line 83 | **Holds as the defect.** Multiple NAME hits leave `geography=None`, so omitted `for_spec` cannot build a URL. |
| `allowed_geographies` is empty unless `len(geographies)==1` | `ask.py` `default_tools`; copied in `test_ask_loop._tools` | **Holds as a second gate.** Even with a selected `matches[0]`, `build_url` aborts unless this set includes that pair. Same PR; not a new tool. |
| `build_url` already falls back to `last_geography` | `tools.py` `for_spec or geography.get("for")` | **Holds.** No schema change. |
| Ranking is one function over class, population, GEO_ID | no `rank_matches` today; no place-name table | **Holds as a requirement.** Named Portland/Springfield/Cook checks are regressions on fake pops, not production branches. Add synthetic Riverton city/town/CDP fixtures. |
| Model-visible result lists every match as equal | `geo.py` `N {level} candidates: {listing}` | **Holds as the defect.** Parallel to CC-54 search summary: `selected …; N alternatives`. Full order stays on the artifact + `ambiguous_place`. |
| `ask.py` is at `max_file_loc` | 400/400; `geo.py` 357/400 | **Holds as a constraint.** Absorb line stays one line (`if matches`). Dropping the `len==1` ternary on `allowed_geographies` frees lines. Ranking lives in `geo.py`. No new module, tool, route, model, or dependency. |
| CC-57 predecessor rates | `evidence/latest.json` / `cc-57-e2e-pre.txt` | **Holds.** long_tail 52/117=0.444; core 6/12=0.500; trap 8/24=0.333; overall 66/153=0.431; p95 18.151s; index_hash `377cd59fe62a`; retriever @10=0.900; selector @1=0.850; alignment 0.544. Do not touch `api/src/retrieval/`. |
| t05 empty URL is still answered | `run_demo.is_answered` `ambiguous_place` | **Holds.** Warning-only still scores. After this PR t05 should keep the warning and may also carry a URL. |

## Decision

Extend the existing NAME listing; rank filtered matches; absorb `matches[0]` whenever the list is non-empty; allow every resolved pair in `allowed_geographies`. Do not add a gazetteer, prompt, or golden-question branch.
