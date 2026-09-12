# CC-52 pre-flight — claims vs measured

Raw classifier output: `evidence/slice-0/cc-52-preflight.txt`.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| `corpus()` loads via `index.load()` against `index_store/` | `grep corpus_identity` / `_ranking_corpus_tables` in `experiments/harness.py` | **Stale.** `7624deb` rebuilds from metadata and applies `_fold_identical_twins`. Live `corpus_n=636` `corpus_hash=fa38e94bcd758cb6`. |
| Committed full-arm results were scored on the pre-fold 756-document corpus | reverse `index_mb` ≈ `n * dims * 4 / 1e6` on every encoder JSON | **Holds** for every full arm (n_est 755–757; 2-decimal rounding). |
| `encoder-gemini-001-sampled40.json` is the same corpus | same reverse-size check | **False.** `index_mb=7.82` → n_est **636** (post-fold). Screening run; not in the ranked table. |
| Reranker JSON corpus | no `index_mb`; they freeze candidates from `encoder-openai-3-large` | Attributed to the same 756-document corpus as that baseline. |
| Neither results nor loader pin a hash | read every `results/*.json`; `run_sweep.py table()` | **Partial.** New writes pin `corpus_n`/`corpus_hash` (`36498b6`). **All 25 committed files still have neither.** `table()` warns only when a hash *exists* and mismatches, so missing hashes are silent. |
| Fold `56aae62` shipped 636 documents | `harness.corpus()` vs `run_codes.pre_fold_corpus()` | **Holds.** 756 `c81155be334e7cfc` → 636 `fa38e94bcd758cb6`. |

## Decision (ticket allowed either)

**Pin the committed results. Do not regenerate Axes A–C.**

Re-running encoders today would score the post-fold 636-document corpus and confound the encoder comparison with the fold Axis E already measured. The published ranks stay the 756-document record; FINDINGS gets a caveat; `table()` surfaces a live mismatch instead of staying silent, and fails on a missing or mixed hash.
