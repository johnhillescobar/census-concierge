# CC-138 post-merge handoff

[PR #134](https://github.com/johnhillescobar/census-concierge/pull/134) integrated GPT-6.2 Sol with the Responses API. [PR #135](https://github.com/johnhillescobar/census-concierge/pull/135) added bounded recovery and preserved the provenance of attempted Census requests. Scoped verification passed on merged `main` at `8f95001a08c21f479bac316cc8bac59eeb81ab27`, with 312 focused Python tests and 112 web tests passing. The candidate and merged revision have identical implementation and test inputs, so the pinned pre-merge cold review, 14 mutation results, and rollback check apply. See the [verification report](e2e-post-pr135.txt) and [closure manifest](../../closure/CC-138.toml).

## What still needs work

The original repeat-3 comparison failed both matched pairs on answer quality. The losses included long-tail or core answers, table selection, rows returned in some families, and more empty long-tail answers. Both repair candidate blocks exceeded 20 seconds p95, at 22.924 and 21.503 seconds. The [owner amendment](https://johnhillescobar.atlassian.net/browse/CC-138) makes the scoped integration contract the acceptance criterion for CC-138. The [four-block results](repair-window-comparison.txt) remain the record of the broader regressions.

| Work | What to verify |
| --- | --- |
| [CC-104](https://johnhillescobar.atlassian.net/browse/CC-104), [CC-106](https://johnhillescobar.atlassian.net/browse/CC-106), [CC-119](https://johnhillescobar.atlassian.net/browse/CC-119), [CC-105](https://johnhillescobar.atlassian.net/browse/CC-105) | Authoritative structured intent, published geography levels, complete parent chains, and row coverage across parents. |
| [CC-129](https://johnhillescobar.atlassian.net/browse/CC-129), [CC-130](https://johnhillescobar.atlassian.net/browse/CC-130), [CC-131](https://johnhillescobar.atlassian.net/browse/CC-131), [CC-122](https://johnhillescobar.atlassian.net/browse/CC-122), [CC-115](https://johnhillescobar.atlassian.net/browse/CC-115) | Vintage and ACS product, variable and universe grounding, reconciliation before execution, operations over returned rows, and alternative-table recovery. |
| [CC-133](https://johnhillescobar.atlassian.net/browse/CC-133), [CC-132](https://johnhillescobar.atlassian.net/browse/CC-132) | Apply the completed measurement contract and establish cumulative release evidence for [CC-3](https://johnhillescobar.atlassian.net/browse/CC-3), including answered rate, table selection, row coverage, empty answers, and the geography grid. |
| [CC-125](https://johnhillescobar.atlassian.net/browse/CC-125), [CC-126](https://johnhillescobar.atlassian.net/browse/CC-126), [CC-127](https://johnhillescobar.atlassian.net/browse/CC-127) | Measure reranking latency in clean windows, Census hang behavior, and memory during demo and metadata work. The CC-3 p95 ceiling remains 20 seconds. |

## Test handoff

- **CC-138 integration.** Keep the request settings and stateless replay tests, deterministic validation and bounded recovery, Census URL and attempted-request provenance, response fields and client compatibility, and rollback and diagnostic model override checks. The merged-main run covers the owner-amended integration scope.
- **CC-139 final grading.** Once the enabling CC-3 changes land, compare GPT-6.1 Sol and GPT-6.2 Sol in one planned experiment on the same corrected workflow. Pin the application revision, exact model versions and settings, cohort, scorer, and controlled inputs. Report factual scores against planned denominators, including failures and unknowns, and report interpretation, executed primary-answer correctness, and recovery separately where supported. Record differences from [CC-137](https://johnhillescobar.atlassian.net/browse/CC-137) and publish an evidence-only PR. CC-132 carries cumulative release certification.

## Publication and Jira handoff

Publish this note, the scoped post-merge report, and the manifest update in one evidence-only PR to `main`. After the owner merges it, verify the manifest on the merged revision, post the integration and follow-up test results on CC-138 as part of its Done transition, and post the grading prerequisites and test plan on CC-139.
