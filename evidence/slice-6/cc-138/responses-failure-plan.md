# CC-138 Responses failure follow-up

Base `84c3c80ae38d661028fd35c31c9feb44d67370ca` (PR #134). The owner requested a fix for the reproduced wrong-table result. This batch covers the local API change, regression tests, documentation, and gate evidence.

| ID | Expected outcome | Check |
| --- | --- | --- |
| AC1 | A provider error or incomplete response returns only the artifacts collected before the failure | `/ask` wire tests before discovery, after retrieval, and after URL construction |
| TC1 | Overall incomplete responses never dispatch their tool items | Wire regression supplies a completed search item within an incomplete response |
| TC2 | A validated URL, retrieved candidates, and any fetched rows survive failure | Wire regressions and existing post-fetch failure test |
| TC3 | Successful tool-loop completion, replay, HTTP response shape, and request settings continue to work | Existing Responses and API contract tests |

Pre-flight used the merged application and a mocked provider with the same question and candidate pool. The completed loop chose `B01003`. When the first provider call returned 503 or an incomplete response, the application instead built a URL for `B19013`, the first candidate. All three requests returned HTTP 200. The benchmark does not record a provider failure trigger, so attribution of the live misses is open.

The six new wire cases ran against the merged implementation before the fix. All failed because fallback returned a row after the model call failed.

Implementation choice (default): return the assembled record on provider failure and retain a built URL if present. The normal finish path can re-resolve geography, replace URLs, and infer requested years. It is appropriate after a normal stop and stays outside the provider failure path.
