# CC-25 acceptance criteria — how each one is evaluated

Evaluated against Jira CC-25, not restated from chat. Tests do not assert on LLM
prose or prompt wording.

| AC | Evaluated by | Result |
| --- | --- | --- |
| Declared body includes answer, url, rows, moe, geoid, universe, table_id, alternatives, warnings on every path | `test_assemble_emits_every_declared_field`; `test_aborted_loop_still_returns_every_contract_field`; `test_openapi_documents_post_ask` required list; `test_a_valid_question_returns_the_declared_contract` | Pass |
| Census URL includes dataset, vintage, all requested E/M, complete for/in, and remains present when fetch fails or returns no rows | `test_scripted_loop_fills_url_rows_geoid_and_universe` parses path + query; `test_failed_fetch_still_returns_the_built_url`; `test_fetch_with_no_rows_still_returns_the_url` | Pass |
| Every ACS estimate is fetched and returned with its matching 90% MOE; empty/unrelated moe does not satisfy | `test_each_estimate_is_returned_with_its_matching_margin`; `test_missing_margin_stays_visible_as_none`; `test_pair_margins_adds_m_beside_every_e` | Pass |
| Every data row exposes a Census-compatible GEOID for TIGER joins | `test_every_row_carries_an_affgeoid`; `test_many_rows_do_not_name_one_geoid`; scripted loop `GEO_ID=0500000US48201` | Pass |
| Universe is the selected table's published universe for the chosen dataset and vintage | `test_universe_comes_from_the_requested_vintage`; `test_empty_matrix_universe_falls_back_to_the_search_hit` (ACS5 2016–2019 matrix strings are empty) | Pass |
| Alternatives are structured `{table_id, reason}` (universe, distribution versus median, collapsed, race iteration) | `test_alternatives_say_how_they_differ` | Pass |
| Census API keys absent/redacted in URLs, exceptions, logs, evidence; remaining URL reusable | scripted loop `key` not in query; `test_census_url_*`; fetch error tests; abort path does not leak `secret` | Pass |
| Response models generate a stable, explicit OpenAPI schema | `test_openapi_documents_post_ask`: `$ref` to Alternative/AskWarning, `url` is a string not an array, descriptions present | Pass |
| alternatives and warnings are typed arrays; Slice 1 exposes one singular url; URL not in prose-or-row keys | OpenAPI items/`url.type`; `assert "url" not in response.rows[0]`; `assert "items" not in url` | Pass |

Out of ticket: five guards (CC-22), `run_demo.py` (CC-26).
