# CC-94 pre-flight — claims vs measured

Raw command output: `evidence/cc-91/cc-94-preflight.txt`.

Settled on `main` @ `91471dc`. Post-merge DEMO/MISSES:
`evidence/slice-3/cc-93-e2e-post.txt`. `evidence/latest.json` is the last
`merge_evidence()` artifact (186 trials), not a reconstructed stub.
Jira `CC-94` In Progress, parent CC-91. Did not Read E2E transcripts.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| Recurring IDs may no longer miss after CC-76 / later leaves | CC-93 post-merge MISSES printout: `q15` and `q41` are gone. Still missing: `q10` `q17` `q18` `q20` `q34` `q39` `t07`. `q08`/`q43` are 1/3 only | **Holds.** |
| Misses can come from different stages | search() @10 + selector misses + demo URLs. Four long-tail out-of-pool (`q17` `q18` `q20` `q34`) equal the 0.90 `@10` remainder. `q10` is selector B-over-C. `q39` is never-built with B25004 in pool | **Holds.** |
| Group by mechanism, not topic | `q20` (mobility) and `q34` (class of worker) share only "expected table out of top-10". Different titles/universes. Not one implementation | **Holds as a constraint.** |
| CC-93 / CC-95 / CC-96 already own some groups | CC-93: remaining empty URLs have `url=''` on the scoreboard — never-built, not a wipe. CC-95: `q10` r3 `place:63116` `state:42` is a published-name Queens. CC-96: `q17` 2/3 empty + 1/3 Tolland County CT | **Holds.** Do not duplicate. |
| Floors can make a miss not worth a leaf | `retrieval_at_10` 0.90 and `selector_at_1` 0.875 already meet gates. Post-merge `answered_rate` 0.850 (printout); generated `latest.json` 0.825 | **Holds.** |

## Decision

One unowned shared mechanism is worth a leaf: finish/`place_token` keeps the raw question, so NAME listing misses an unambiguous published place (`q39` 3/3 empty; `t07` empty path). Recommend no retrieval, B/C, or pin leaves. Informal regions stay CC-96; Queens PA stays CC-95.
