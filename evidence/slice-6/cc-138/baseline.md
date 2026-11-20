# CC-138 pre-implementation live baseline

The run measures `cc-138/model-integration` at `27d4d4711f577cf91bb78890b1dd32ff82c766ed`. The existing Chat Completions path uses `gpt-4o-mini`. The unchanged `scripts/run_demo.py --repeat 3` uses all three normal tiers through `POST /ask`. It uses the root environment and the root `index_store`, with stdout and stderr captured to the baseline transcript.

| Input | Recorded identity |
| --- | --- |
| Demo scorer hash | `6054312479188110` |
| Metric protocol hash | `8239289b06c79e1f` |
| Core cohort hash | `3f0faaf0e5df706b` |
| Long-tail cohort hash | `3357c07b051d8f28` |
| Trap cohort hash | `86599fef7d3afc08` |
| Prompt hash | `79910a5885fc` |
| Retrieval index hash | `377cd59fe62a` |
| Availability artifact SHA-256 | `cca2cc4b4f9541f409116f7c76de888a8ddc0b92040ab41cbae6840f81d250d6` |
| Census metadata cache manifest SHA-256 (95 files) | `fa760dfb8c7d95234d84b427dc3ead6cf08c07028022045b81eef4dd9d8fefcb` |
| Served frontend manifest SHA-256 (4 files) | `17a909a66cbb00dbd11125545dde096fb55eeb3ef8ef95dd8b6bf8445b95805b` |

Each manifest hash covers the concatenation of the sorted UTF-8 relative paths, each followed by a NUL and the corresponding binary SHA-256 digest.

## Initial setup attempt

The attempt completed at 00:02:45 UTC on 2026-11-20 with exit status 1. All 186 trials scored zero and averaged zero measured model or Census time. An independent worktree setup check reproduced `FileNotFoundError` loading `index_store/availability.json.gz` in the pre-model tool setup path. `INDEX_STORE` supplied the lexical and semantic index. The availability artifact and `data/raw` metadata cache resolve from the checkout itself.

The recovered setup copies the ignored availability artifact and all 95 metadata cache files from the root checkout. SHA-256 verification matched the source bytes, and `default_tools()` loaded all four tools. The recovered run used the same pinned commit and command.

- [Initial transcript](e2e-baseline-setup-failed.txt), SHA-256 `fd22cf9a667f79690bb9848e770aba840dff3e8cd6a696851aab96915de759a1`
- [Initial scoreboard](baseline-setup-failed-scoreboard.json), Git LF SHA-256 `a197b14a46181dabe6a1d95d6e20d60511ad5c2acc15f8b76478b89c1999ce78` (original Windows snapshot `1e75726a605f2ccd3ee5eaac985a7495e0532fc2785b710635ef2da08b9bcbfb`)

## Live-run diagnostic

The aggregate heartbeat paused at 10 of 186 trials from 00:07:07 UTC for more than ten minutes. A nonblocking Python stack snapshot without local variables showed the FastAPI test client awaiting the retrieval worker. The worker was waiting for TLS response headers from OpenAI `embeddings.create`, called by `index.search` through `embed_query`. The pinned embedding model is `text-embedding-3-large` and the installed OpenAI SDK allows a 600-second read timeout and two retries by default.

The same process resumed and reached 37 of 186 by 00:24:02 UTC. The run retained its original model, timeout, retries, credentials, and runtime assets.

## Recovered live run

Completed at `2026-11-20T01:02:40+00:00` with exit status `1`. Provenance records the pinned head and clean measured paths. The run scored all 186 planned trials.

| Gated measure | Observed | Budget | Status |
| --- | ---: | ---: | --- |
| Long-tail answered rate | 0.700 | >= 0.700 | PASS |
| Full-suite p95 latency | 25.960 s | <= 20.000 s | FAIL |

| Tier | Trials | Answered rate | HTTP OK rate |
| --- | ---: | ---: | ---: |
| core | 12 | 1.000 | 1.000 |
| long_tail | 120 | 0.700 | 1.000 |
| trap | 54 | 0.981 | 1.000 |

Overall answered rate was 0.801. Mean measured times were 10.379 s for the model, 3.752 s for Census, 3.897 s for reranking, 0.346 s for embedding, and 0.413 s for remaining application time.

- [Live transcript](e2e-baseline.txt), SHA-256 `45a5bff170af4d8ed27a08dfa65c3f6bfc3563eef5b5673c92ac60256e065f44`
- [Live scoreboard](baseline-scoreboard.json), Git LF SHA-256 `694bd31c53fc17ee000e9caa13c6a47eda597c8052265424466c137a890a3ef1` (original Windows snapshot `a78f4d6f2cfa49f6e349870569f88cbe8c7380be722411130e8a490ce30b23b0`)
