Owner clarification, 2026-11-19

Apply regression gates during each implementation story. Establish the applicable baseline and focused regression checks early, then run the existing implementation gates on that story’s changes. The final model grading in CC-139 is a separate, gate-free experiment after its linked fixes land. The experiment has no permanent software changes. Existing story criteria, early measurement ownership in CC-133 and release certification in CC-132 continue to apply to the implementation work.

Metric progression refinement
CC-133 owns early instruments, baselines and automated AC/TC enforcement; it blocks migration shipping after CC-114. CC-132 owns final certification only. All earned capability floors are cumulative. See each story for its owned target; no invented predicted percentage-point gains.

Gate: docs/playbooks/run-slice.md; scripts/closure.py checks the AC/TC record, and scripts/metric_compare.py judges measured runs by evals/metric_protocol.toml.

Owner-approved alignment — 2026-11-08
Objective: the model understands a Census question using grounded metadata; deterministic execution faithfully follows structured intent. Follow-ups preserve meaning across turns. This replaces earlier ordering instructions and any allowance for legacy prose fallbacks, without reopening Done children.

Model-owned intent (owner alignment 2026-11-08)
Once the model supplies structured intent, deterministic resolution, validation, URL construction, fetch, computation and recovery use that intent, authoritative Census metadata and execution artifacts. They must not reinterpret original question wording, paraphrases or reconstructed English commands. This prohibits regexes, keyword/substring matching and equivalent semantic heuristics, including legacy fallbacks. Missing or invalid intent returns structured feedback for bounded model repair. No missing, late or uncertain report activates a prose parser.
Original text belongs only in model interpretation, semantic retrieval/reranking, storage, display and audit; deterministic execution inputs must not expose it indirectly through a broad record. Exact identifier parsing, metadata lookup, matching an already-identified entity to NAME candidates, URL encoding and arithmetic remain legitimate. Name lookup must not infer scope, parents or level from a sentence.
Keep requested intent separate from executed plans and explicit defaults/assumptions/deviations. Preserve grounded candidates, the editable plan strip and the level-incomplete no-URL refusal; no blocking question, fabricated data or unrelated national/total-cell fallback. Unsupported availability is distinct from misunderstanding. One existing loop, no second planner or validator stack, no budget raise.

Understanding release gate (new requirements; not a claim of current performance)
At --repeat 3, require >=98% joint interpretation accuracy overall, >=95% in each critical category, and a 95% confidence lower bound >=95% overall on BOTH frozen regression and owner-held sealed suites. Joint correctness requires all applicable meaning-bearing fields: measure/universe, geography identity/level/scope/coverage, time/product, requested cells, operation and follow-up changes. Report case pass (correct in >=2/3 repeats) AND trial accuracy; both point rates must meet their thresholds. Confidence is computed over independent question families, not repeated trials or paraphrases as independent samples.
Use at least 200 independent question families per suite, with >=30 families per critical category; categories may overlap. Include genuinely new compositions, ambiguity, incomplete requests and unavailable-data controls. Freeze expected structured interpretations and permissible alternatives before results. Human/domain-reviewed expectations plus real metadata are the oracle; self-confidence or agreement between models is not ground truth. Show 95% intervals per category and a predeclared family-resampling method.
On the supported, unambiguous, answerable subset, >=95% must receive a determinate interpretation (coverage) and >=98% of determinate interpretations must be jointly correct. Blanket refusal or warnings cannot inflate accuracy. Ambiguity/unsupported cases use independently defined expected outcomes and separate rates. Zero silent substitutions and fabricated results in the finite acceptance suite. Distinguish interpretation, faithful execution, and end-to-end semantic results; HTTP 200 and correct table alone do not pass.
These are new target gates, not budget.toml edits or guarantees over all future inputs. The evaluation story implements them before claiming near-perfect understanding. If data, sample size, latency or quality is insufficient, release readiness remains unverified; do not lower thresholds or quietly narrow supported coverage.

Acceptance criteria
AC1. Every in-scope child AC/TC is cleared with evidence. CC-114 finishes its advanced scoped work first; CC-104 then migrates the shared boundary without duplicating it.
AC2. Zero silent level/scope/coverage/time/cell/operation substitutions in acceptance suites. Unsupported data is explicit and never invented. URL, MOE, GEOID, universe and alternatives retain their existing response/refusal contracts.
AC3. Close CC-129, CC-130, CC-131, CC-132 and CC-133, plus all existing children; schedule CC-122 bounded operations in this slice. Subject/profile/other product-family expansion and general crosswalks are not silently added.
AC4. Retain single-turn long_tail >=0.712 against the historical 0.742 baseline until CC-42 re-anchors; afterward apply the stricter B/P/A/L observed non-regression and uncertainty gates above, retaining the fixed migration anchor and earned floors. Report instrument changes separately and rebaseline before claiming code gains.
AC5. Retain existing multi-turn case floors: swaps >=5/6, additions >=4/6, unresolved >=5/6, passing in >=2/3 repeats; trial rate >= single-turn long_tail minus 10 points; CC-107/108 standalone-equivalence >=80%. New understanding gates are additional, stronger measures.
AC6. Retain visible dev/frozen regression/owner-held sealed separation, leakage prohibition, at most one sealed run per story close, and regression-minus-sealed gap <=10 points with family-level intervals. No sealed or E2E transcript reads. Preserve >=18 multi-turn sealed cases, with the new semantic suites providing the larger release sample.
AC7. Record actual demo.p95_latency_seconds <=20s and existing code/tool/model/dependency budgets. CC-113 is Done; CC-125/126 remain Phase 2 backlog and are not current-slice prerequisites; over-ceiling current results remain blocking without a valid owner waiver. No implicit budget waiver, new model, or threshold reduction.
AC8. Follow-up context has the existing <=1.0s t_llm p50 increase cap if latency findings are not implemented; record deltas regardless. Every URL remains redacted.

Execution order and dependencies
CC-114 current implementation/gates/E2E closeout first. CC-133 instrument/AC-TC manifest work starts alongside without changing CC-114 scope. CC-133 must establish the instrument and anchor before migration shipping. Then CC-104 -> CC-106 -> CC-119 -> CC-105. CC-129 and CC-130 follow CC-104; CC-115 follows relevant override-contract changes. CC-118 requires CC-133 but is independent of geography implementation; CC-82 requires CC-102 (Done), CC-118 and CC-130. CC-131 uses grounded geography, CC-129 and CC-130; CC-122 follows CC-130/CC-129 and CC-82. CC-42 baseline follows geography, time, cell selection and understanding work, using completed CC-120 grid; CC-43 requires CC-42 and CC-82 -> CC-107/108 -> CC-39. CC-132 final release gate runs after all scoped paths and CC-122. Do not mark instrument preparation as completed release proof.

Test cases
TC1. New phrasings/compositions correctly identify joint intent across every critical category.
TC2. Fixed intent and metadata yield identical deterministic execution despite changed/absent outer wording, including recovery failures.
TC3. Correct table but wrong cells, scope, parents, periods or calculation fails semantic scoring.
TC4. Ambiguous, incomplete and unavailable requests receive their correct distinct outcomes without invented facts or blocking questions.
TC5. Three-turn changes preserve unaffected intent and separate result legs.
TC6. Missing/failed/unverified AC/TC blocks shipping and Done; post-merge evidence is required.

Owner-approved audit tightening — 2026-11-13

Why this is important

Clarify the epic's product promise: correct primary answers and useful selectable alternatives require separate evidence, and digit-free qualitative statements still need grounding.

Acceptance criteria additions

AC1. Final certification separately establishes interpretation, primary end-to-end semantic answers, offered-alternative correctness, executed alternative recovery and material qualitative-claim grounding under CC-132. Retrieval@10 and the 98% interpretation target do not imply an equivalent final-answer or recovery rate.

AC2. CC-115/130 own semantically valid alternative selection and candidate/executable distinctions; CC-122/131 own supported qualitative claims. CC-121 remains Done with its historical numerical-rendering scope; these additions do not retroactively certify it as verifying all prose.

AC3. Special epic CC-136 resolves model selection and integration before completing CC-104, then remaining CC-3 work. Any changed model/latency constraints require an explicit scoped amendment at integration; current quality floors and budget rules remain in force.
