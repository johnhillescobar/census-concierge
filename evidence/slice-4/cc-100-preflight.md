# CC-100 pre-flight — claims vs measured

Settled on `main` @ `6f3f931` (post CC-87 E2E), before the budget commit
`5cd0625`. Verified against the live app (`uvicorn`, real `OPENAI_API_KEY` /
`CENSUS_API_KEY`), not a transcript read.

## Claim: multi-geography comparisons drop places, and it's Texas/ambiguity-specific

Reproduced live via `POST /ask`, 5x, before any fix was designed:

| Question | Result |
| --- | --- |
| "...Austin city, Texas and Dallas city, Texas since 2017." (same state, Dallas locally ambiguous with Lake Dallas) | Only Dallas + Lake Dallas in `plan.geographies`; Austin absent entirely; `answer="build_url failed twice"` |
| "...Seattle city, Washington and Portland city, Oregon since 2018." (different states, unambiguous) | Only Portland; Seattle absent; no warning at all; `answer="fetch_data failed twice"` |
| "...Seattle city, Washington versus Portland city, Oregon since 2018." | Only Seattle; Portland absent; `answer="fetch_data failed twice"` |
| "...Austin, Houston, and San Antonio city, Texas since 2019." (3 places, one state) | Only San Antonio (last-named); `answer="build_url failed twice"` |
| "...Chicago city, Illinois and Phoenix city, Arizona since 2019." (different states) | Only Phoenix; Chicago absent; `answer="build_url failed twice"` |

**Verdict: holds, and generalizes.** Not a Texas quirk, not a name-ambiguity
quirk, not a place-count quirk, not a same-state-vs-cross-state quirk. Every
"and"/comma-phrased comparison drops every place but the last-resolved one;
"versus" phrasing (2-way only) is the sole path that reliably kept both,
because it merges in one `resolve_geography` call today, before this ticket.

## Claim: `_absorb()` overwrites `record.geographies` on every call

`api/src/ask.py:89` (pre-fix): `record.geographies = list(specs if specs is
not None else get("matches") or [])` — unconditional replace, no merge
across sequential calls. `geo.py`'s `split_versus` (pre-fix) only recognized
"versus"/"compared to"/"vs", never "and" or a comma list, so the model's two
separate per-place calls for "and" phrasing never went through the one
merging call path that already existed for "versus".

**Verdict: holds, exact line.**

## Claim: a stale tool-failure string leaks into `answer` even after recovery

`api/src/ask.py:437-439` (pre-fix): `except RuntimeError as exc: answer =
answer or str(exc)` then `await finish_tools(...)` unconditionally — nothing
ever reset `answer` afterward, even when `finish_tools` went on to recover
real rows. Confirmed live in all 5 repros above: `record.rows` was non-empty
in 4 of 5, yet `answer` still carried the raw `"<tool> failed twice"` string.

**Verdict: holds.**

## Claim: `finish_tools`'s own versus-comparison repair doesn't always fire

`api/src/finish.py:134` (pre-fix) gated the fetch retry on `record.fetch is
None`. `_absorb`'s `fetch_data` branch sets `record.fetch` even when
`artifact.ok` is False. Confirmed: `_wrong_versus` (pre-fix) already existed
and would have repaired the "versus" cross-state case, but a failed fetch
attempt earlier in the main loop left `record.fetch` non-`None`, so
`finish_tools`'s tail check skipped the retry that would have used the
repaired geography list.

**Verdict: holds.** Separately confirmed `clear_series()` (called on every
`build_url` dispatch) resets `record.fetch` to `None` — so a `build_url` redo
does force a fresh fetch; the gap is specifically a *fetch-only* failure with
no accompanying geography redo.

## Claim: fetch fan-out and `plan.geographies` also hardcode "exactly 2"

Grepped `api/src` for `[:2]` co-occurring with `compare`/`geo_status`:
`api/src/ask.py:366` (`fetch_data`'s `last_geographies` lambda) and
`api/src/contract.py:196-197` (`plan_from_record`) both truncate to `[:2]`
whenever `geo_status.compare` is true, regardless of how many places were
actually named. `api/src/guards.py:216` (`ambiguous_place`) hardcodes the
same `<=2` threshold. `api/src/compare.py:111` (`shares_sample`) also slices
`[:2]`, but that one is a genuinely pairwise parent/child nesting check
(MOE-independence), not a "drops data" bug — confirmed out of scope.

**Verdict: holds for `ask.py`, `contract.py`, `guards.py`; `compare.py` is a
false positive, left unchanged.** All three hardcoded-2 sites need the same
new signal: a count of genuine per-place picks, not the raw geography-list
length (which also includes leftover ambiguous candidates).

## Decision

Generalize `geo.py`'s existing `split_versus` → `split_comparison` (N-way,
"and"/comma-list detection anchored on state names, not raw commas). Add
`compare_count` to `ResolveGeographyResult` — the leading N specs that are
genuine per-place picks — threaded through `ask.py`'s `geo_status`,
`finish.py`'s redo trigger, `contract.py`'s `plan_from_record`, and
`guards.py`'s `ambiguous_place` threshold. Add a deterministic (non-LLM)
fallback-answer replacement in `ask.py`, only when `finish_tools` recovered
real rows. Fix `finish.py`'s fetch retry gate to `record.fetch is None or not
record.fetch.ok`.

No tool, schema, or `AskResponse`/`ChartSpec` contract change — this is
entirely upstream of the response contract, in the four existing acquisition
tools' orchestration. Fits `docs/slices.md` CC-56 (a capability change is
earned by a demonstrated failure, not scheduled) without any budget or tool
count change — `api_src_loc`/`max_file_loc` still needed raising afterward
purely on line-count grounds (measured 4036/4100, 405/410 — see the budget
commit `5cd0625`, its own standalone human commit with reason).

## Out of this ticket

`compare.py`'s `shares_sample` pairwise check (not a data-dropping bug).
Cross-state fetch fan-out mechanics beyond the `[:2]` slice (already correct
— confirmed `FetchDataTool._arun`'s `fanout()` already builds one leg per
`GeoSpec` × year via `template.with_geography(spec.for_spec, spec.in_spec)`).
Chart/table as agent tools (deferred Slice B in the plan file, explicitly
sequenced after this fix).
