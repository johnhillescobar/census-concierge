# CC-103: how we got from 5% to 99% on multi-parent listings

Ticket: CC-103, "multi-parent wildcard listings like 'all counties in Texas and Louisiana'
collapse to one parent for most phrasings." Work ran 2026-10-02 to 2026-10-04 on branch
`cc-103/multi-parent-repair`. This is the story of the experiments, with the numbers. Only
aggregates appear here; sealed question text, sealed logs and sealed phrasing are not in
the repository and were never read by the agent doing the work.

## 1. Result in one table

Same task, four builds, tract level (the hard level: one wildcard URL per named county).
Held-out = the owner-held sealed set, 38 cells x 3 repeats = 114 trials, scored with the
county-identity check.

| Build | Visible tract (144 trials) | Held-out tract (114 trials) | Gap (visible - held-out) | `long_tail` demo p95 |
|---|---|---|---|---|
| `origin/main` (before) | 10.4% | 8.8% and 6.1% (two runs) | | 20.19s |
| C0: parent-split call + first prompt | 138/144 = 95.8% | 98/114 = 86.0%, 101/114 = 88.6% | +9.8 / +7.2 | 19.80s |
| **C1: parent-split call + v4 prompt (shipped)** | **143/144 = 99.3%** | **108/114 = 94.7%** | **+4.6** | **17.15s** |
| C2: v4 prompt, parent-split call off | 1/144 = 0.7% | not run | | 20.49s |

The shipped build answers a multi-parent listing correctly about 19 times in 20 on
phrasings it has never been tuned on, up from about 1 in 12.

## 2. The problem

A user asks for something like "every tract in Cook and DuPage County". The model's own
`resolve_geography` call usually collapsed it to one parent, picked the wrong level, or
treated it as a comparison. The URL is the product, so a one-parent URL is a silent wrong
answer. It depended on phrasing: some verbs and connectors worked, most did not.

## 3. How we measured (the part that made the rest possible)

- **A phrasing grid.** 70 visible cells = verb x connector x parent count x county/tract
  (`evals/cc103_phrasing_grid.toml`). The owner split a held-out part off by verb into a
  sealed set outside the repo (hook-blocked), 38 cells at tract level.
- **Scorer** (`scripts/run_grid.py`): a cell passes when the fetched URLs cover exactly one
  distinct parent per expected parent, at the right level, with rows. Resumable batches,
  runs through a TestClient, logs status, warnings and crash type per trial.
- **Identity check, added late** (`tract_identity_ok`, `scripts/rescore_grid.py`): a trial
  passes only if its tract URLs name the counties the cell names, in one state. It caught
  about 10 points of false passes on option B (same-named counties in the wrong state).
  The rescorer prints counts only, so it is safe on sealed logs.
- **Ambiguity labels** come from the Census Gazetteer by set membership
  (`scripts/label_grid_ambiguity.py`), not from a model or a regex. Two model-based labelers
  were tried and rejected as unreliable (`ambiguity-*-unreliable.jsonl`). The definition
  went into `docs/requirements.md`: ambiguity means a place name that can denote several
  geographies and the question picks none; scope ("which counties?") is not ambiguity.
- **Nondeterminism:** one run tells you nothing, so every comparison is at a fixed
  `--repeat` (three runs of 48 visible trials, 114 sealed trials). About +/-5 points is the
  noise band at these sizes.
- **Guards:** budgets (`budgets.toml`, never raised by the agent), a regex ratchet in
  `check_invariants.py` (the count of `re.*` call sites in `api/src` may only go down),
  leakage rule (no eval phrasing or place in prompts, tool text or `api/src` literals), and
  a 10-point ceiling on the visible-minus-held-out gap.

## 4. Timeline of approaches

### 4.1 First repair: ask the model again after the loop (`0903ffa`)
`finish_tools` asks the model once for `{parents, unit, listing}` and re-runs
`resolve_geography` with every parent. Code only validates (closed unit set, parent count,
nested and all wildcards) and otherwise restores the loop's own answer. No regex. It left a
known gap: results the loop had marked as comparisons were skipped.
Visible-grid pass rates during these iterations ranged 41% to 83%
(`cc103-grid-post-v1..v3`).

### 4.2 Base build (`5d16fb0`): let the model decide for every result
Removed the comparison skip and the single-named-place gate. Visible tract 77.1% -> 89.6%
(43/48), but the demo p95 was 22.80s, over the 20s ceiling, because the repair call ran
serially after the loop. Not shippable; it became the base for two options.

### 4.3 Option A vs option B, decided by a rule set before the numbers
Rule (agreed 2026-10-03, before results): eligible only if clean demo p95 <= 20s and
tests/budgets/invariants pass; then compare held-out tract pass rate and the gap; scores
within about 5 points tie; then smaller gap, then simpler code; also run the base build on
sealed. The owner stressed that the drop from visible to held-out is the dealbreaker.

- **A** (`c8948e7`): start the parent-split model call beside the loop as an asyncio task
  (`split_beside`), reuse its result in `finish_tools`; no model call after the loop.
- **B**: no extra call; the loop's own `level` and `parents` carry the structure. Much less
  code (80 insertions, 417 deletions) but prompt-sensitive: its first two prompt attempts
  scored 3/48 and 2/48 (a third reached 28/48).
- Sequential runs on separate branches with commits; the loser's branch was deleted and
  kept as tag `cc-103-opt-b-rejected`.

| | Visible tract | Held-out tract | Gap | p95 | Eligible |
|---|---|---|---|---|---|
| A | 131/144 = 91.0% | 107/114 = 93.9% | -2.9 | 15.63s | yes |
| B | 110/144 = 76.4% (after identity check) | 83/114 = 72.8% and 74/114 = 64.9% | +3.6 / +11.5 | 21.33s | no (p95) |
| Base | 43/48 = 89.6% | 108/114 = 94.7% | -5.2 | 22.80s | no (p95) |

A won on eligibility and on accuracy: B lost 21 or more points on held-out once the
identity check was applied, and its second sealed run broke the 10-point gap ceiling.
The measurement tool mattered: before the identity check B looked like 81.6% held-out.

### 4.4 Gate 2 (cold review) and a regression we caused
Cold review of A found real defects, and fixing them taught the most expensive lesson:
- Repair acceptance judged all geographies, but the resolver returns the chosen parents
  first and same-named ambiguity candidates after them; correct repairs were rejected. Fix:
  judge the first `len(parents)` (`110e1be`).
- A prompt example named a place that is also an eval place (a leakage-rule breach).
  Replacing it with generic wording made the model drop the state from four-county lists
  and the visible tract score fell to 116/144, then 107/144. A one-shot format example
  with a place absent from every eval file restored it (`b84430f`).
- Also hardened: acceptance needs at least as many wildcard geographies as parents; an
  accepted repair clears the old url/rows/fetch; a rejected repair restores
  `retained_urls`; waiting on the split is capped at 6s and real cancellation is no longer
  swallowed. Each change has a test that fails under its mutation.
- Result: the final C0 build, 138/144 visible, 86.0% to 88.6% held-out. Held-out was lower
  than the earlier A head's 93.9%, at the edge of the noise band.

### 4.5 The prompt experiment (C0, C1, C2)
The owner supplied a new main-loop prompt: decide listing vs comparison first; for
listings send `parents` and `level` in one call; normalize every entry as "Place, ST";
other same-named matches are candidates, not selections. Measured one condition at a time
on its own branch, prompt hash recorded (`prompt-v4-c0e048fc86b5.txt`).
- At 977 tokens by the budget counter it fit the 1,200 cap, so the planned trimmed variant
  and the budget-raise question dropped out. Only the `level` tool description changed,
  to list the valid names the prompt points at.
- C1 (v4 + repair call): 143/144 visible, 108/114 held-out, p95 17.15s. C0 was beaten on
  every measure.
- C2 (v4, repair call off): 1/144. The prompt alone does not replace the extra model call
  on this code. (This does not show that no prompt-only design could work: option B had
  its own resolver handling for first-call `parents`, which C2 does not.) Kept at tag
  `cc-103-c2-rejected`.

## 5. What went wrong on the way (kept, because it is the point)

- **A bad mutation check corrupted the source** (`sed -i` mutated a `status.get("compare")`
  to `False`). Runs from that build are kept apart under `invalid-corrupted-build/` and were
  not used. The harness changed to save-copy, apply, test, restore.
- **The scorer overstated B** until the identity check existed (about 10 points).
- **A partial sealed summary was mistaken for a final one**; the summaries now carry
  `trials`, `expected_trials` and `complete`.
- **A fresh worktree had no `.env` and no git-ignored data folders**, so a "B rerun" scored
  0/114 with 114 `FileNotFoundError` crashes in seconds. It was caught because the crash
  type is logged and a 0.0 is treated as a harness failure, not a result.
- **Re-running a completed tag silently overwrote its log.** New tags per run from then on.
- **The harness printed sealed question text on a miss.** Output to a file or `$null` for
  sealed runs; the agent never used the text.
- **Timestamps were read as UTC when they were local**, which briefly mislabeled which build
  a sealed log came from. `_sealed_final`'s build is therefore unverified, and the
  verified-build run is `_sealed_final2`.
- **A rename (`ROLE` to `PROMPT`) crashed the demo script** that hashes the prompt; the
  C1 demo had to be rerun. The stale `latest.json` was almost taken for the new result.

## 6. Working rules that came out of this ticket

- **Regex is a last resort** (CLAUDE.md and the Cursor rule, merged in PR #98): allowed only
  after plain code and the model were both tried and failed, with up to 100
  solve-and-measure iterations and 3 subagents shown in the PR, cheapest first. Every
  step above that needed to understand a question was given to the model, with code
  validating its structured output.
- **Sealed discipline:** the agent never sees sealed questions, only counts; sealed outputs
  are git-ignored; sealed runs use a new tag each time; a sealed set used to pick between
  options is slightly optimistic for the winner.
- **Budgets are human commits.** `api_src_loc` was raised to 4400 by the owner for this
  ticket. The shipped build uses 4,396.

## 7. Shipped configuration and what is left

- `api/src/finish.py`: `plan_split`, `split_beside` (concurrent), `_split_parents` with
  snapshot/restore; `api/src/prompts.py`: the v4 prompt (constant `ROLE`, hash
  `c0e048fc86b5`); `api/src/tools.py`: `level` names. The tests assert behavior, never
  prompt wording.
- Open follow-ups, none blocking: a silent-repair warning code (the user is not told when a
  repair changed the answer); resolver selection for same-named places and the noisy
  `ambiguous_place` flag; remaining regexes in `finish.py` and `geo.py` (`_LISTING`,
  `_BY_COUNTY`, level aliases) as migration debt under the ratchet; leftover worktrees
  (`opt-b-sealed`, `rule-regex`, `rule-regex2`) and an old stash entry.
- Gate 2 on the C1 delta (`gate2-c1.txt`): no blocking findings. Budgets and invariants pass,
  lint is clean, 599 tests pass. One LOW note, not from this ticket: the `query` description
  in `api/src/tools.py` has contained "all counties in Oregon" since `origin/main`, and the
  same phrase is a golden `core` question, which the no-eval-places rule forbids. It is left
  for the owner to decide. One INFO note: when the loop already sends every parent on one
  wildcard call, the repair is skipped but the extra model call still runs on every request
  (cost, not latency).
- Not yet done at the time of writing: PR, post-merge E2E, and closing the Jira ticket with
  the post-merge numbers.

## 8. Evidence index (`evidence/slice-6/`)

| Path | What it holds |
|---|---|
| `cc103-option-selection.md` | The A/B rule, held-out table, selection reading |
| `opt-a/`, `opt-b/` | Tract x3 and demo per option; B's three prompt attempts |
| `final/`, `final-state-dropped-prompt/`, `final-110e1be-tract-only/` | C0 and the two regressions |
| `c1/`, `c2/` | The prompt experiment; C1 (shipped) and C2 (rejected) |
| `prompt-v4-c0e048fc86b5.txt` | The v4 prompt, verbatim |
| `gate2-*.txt` | Cold reviews, including `gate2-c1.txt` |
| `invalid-corrupted-build/`, `aborted/` | Runs not used, kept apart |
| Tags `cc-103-opt-b-rejected`, `cc-103-c2-rejected` | The two rejected builds |
