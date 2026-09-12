# CC-23 pre-flight — claims vs measured

Raw command output: `evidence/slice-1/cc-23-preflight.txt`.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| Slice 1 may continue (CC-19 shipped the HTTP surface) | `.claude/PLAN.md` STATUS 2026-09-12; `POST /ask` exists | **Holds.** `run_ask` is still a stub. |
| The four tools do not exist yet | `rg` under `api/src` | **Holds.** Hits are comments in `ask.py` only. No `BaseTool`, no `add_node`. |
| Budgets have room for 4 tools, 8 schemas, 1 dep | `check_budgets.py --structural-only` | **Holds.** tools 0/6, schemas 0/12, models 4/15, deps 6/25, files 14/40, LOC 920/4000. `doc_lines` 1799/1800 — **do not add prescriptive docs.** |
| `search()` is the Slice 0 index | `api/src/retrieval/index.py`; loaded index | **Holds.** 636 tables; `search(question, k) -> list[str]`. Default `k=5`; AC wants a top-10 pool so the tool passes `k=10`. Universes and family `members` live on the loaded `Index`, not on `search()`'s return. |
| A family member is recorded, not a free-invented table | `index.members` for `B19013` | **Holds.** `B19013A–I` are members. `B01003` has none. The tool returns the ranked pool; members travel with each hit so later tools can accept them without ranking them as extra hits. |
| `geo_levels()` is the authority on legal `for`/`in` | `metadata.geo_levels("acs5", 2023)["county"]` vs raw `geography.json` | **Fails as written.** `geo_levels()` keys by `name` and last-wins, so `county` is summary level **324** (requires MSA + metro division, no wildcard). The legal "all counties in a state" form is **050**: `requires=["state"]`, `wildcard=["state"]`. `resolve_geography` must scan every `fips` row and pick the predicate whose `requires` match the `in` clause. |
| Within-level wildcard is one Census request | live ACS5 2024 `for=county:*&in=state:41` | **Holds.** HTTP 200, 36 Oregon counties, `GEO_ID=0500000US41001`. |
| Illegal nesting 400s rather than silently substituting | live `for=zip code tabulation area:*&in=county:201` | **Holds.** HTTP 400 `unknown/unsupported geography hierarchy`. |
| Place names resolve to codes without a gazetteer module | live `for=county:*&in=state:*` | **Holds.** 3222 rows; "Cook County" is three candidates (GA/IL/MN). Return them as results — do not pick. Census onelineaddress geocoder matches **zero** county names; do not use it. |
| `build_url` can pair every `E` with its `M` | availability matrix stores `001E` suffixes; live URL with both | **Holds.** Matrix lists estimate suffixes only (`metadata.variables` drops `M`). Pairing is `001E` → `001M` by substitution, then both go in `get=`. Live Oregon URL returned both columns. |
| Latest vintage is not a hardcoded 2023 | availability `acs5` keys | **Holds.** Latest cached ACS5 is **2024**. Read it from the matrix. ACS1 has no 2020. |
| `fetch_data` must not discard the URL on failure | 400 on illegal hierarchy still has a constructed URL | **Holds** as a design constraint. The tool returns `{ok, url, rows, status_code}`; the redacted URL is a field, not only an HTTP success body. |
| `langchain_core.tools` supplies schema + validation | `uv run --with langchain-core` | **Holds, with a catch.** `convert_to_openai_tool` emits the function schema. `ainvoke({...})` without a tool-call id returns **only the content string** and drops the artifact. `ainvoke({"type":"tool_call","id":...})` returns `ToolMessage` with `.content` and `.artifact`. Dispatch must use the ToolCall form so rows never pass back through the model. |
| `create_agent` / graphs are banned | `check_invariants.py`; DESIGN §9 | **Holds.** Hand-rolled `call_model()` + `dispatch()`. No `finish` `BaseTool` — Jira AC says exactly the four named tools; the model stops by emitting text. |
| Full response-contract polish, five guards, `run_demo.py` | Jira CC-25, CC-22, CC-26 | **Out of this ticket.** CC-23 wires the loop and tools. The assembler copies artifacts onto the already-declared `AskResponse`. Guards and the demo harness stay on their tickets. Key redaction cannot wait: URLs with `&key=` must be a `CensusURL` whose default form is redacted. |
| CI has no Census/OpenAI keys and no `index_store/` | `.github/workflows/check.yml` | **Holds.** Tools and the model client are injected per request. Route tests monkeypatch `run_ask`. Fakes that rank the same table for every question are banned. |

## Decision

Ship the four tools and a hand-rolled loop behind existing `POST /ask`. Scan all `geography.json` `fips` rows (do not call `geo_levels()["county"]`). Default ACS5 vintage is 2024 from the matrix. Add `langchain-core` as the 7th direct dependency. Do not add a fifth tool, guards, or `run_demo.py`.
