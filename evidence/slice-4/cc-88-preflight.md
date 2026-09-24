# CC-88 pre-flight — claims vs measured

Raw commands in this file. Settled on `origin/main` @ `92352b6` (CC-89
post-merge). Jira `CC-88` To Do, parent CC-11. Did not Read E2E transcripts.
Did not open sibling story descriptions.

| Claim in the ticket | Settled by | Verdict |
| --- | --- | --- |
| `App` already owns the sole active `AskResponse`, so the living workspace needs no state-management dependency | `rg "useState.*AskResponse" web/src` → `App.tsx` only (`result: AskResponse \| null`). `rg zustand\|redux\|jotai\|recoil\|mobx web/` → no matches. `web/package.json` deps: `react`, `react-dom`. | **Holds.** One field, no store. |
| The current loading path clears or replaces the result and the exact state transition that must change is identified by a failing behavior test | `App.tsx` `onSubmit` called `setResult(null)` before `askFn`. New test `keeps the prior result visible while a later question is loading` failed: `.census-url` was `undefined` during the second in-flight request (vitest 25 tests, 6 failed on the pre-change tree). | **Holds as the change.** Drop `setResult(null)` on submit; keep the prior `AskResponse` until success. |
| Existing URLs, warnings, universe, alternatives, and error states can move into two panes without an API/client change | `api/src/main.py` has one `@application.post("/ask")`. `ask.ts` already `fetch("/ask")`. `normalizeActiveDataset` / `censusUrls` already in `web/src/display.ts`. Pane states already `"idle" \| "loading" \| "error" \| "result"`. | **Holds.** Layout only. |
| The proposed responsive layout fits within existing source/file budgets and does not require a component framework | `check_budgets.py` on `origin/main`: web src LOC 1315 <= 3000; api src LOC 4000/4000 (no api edit). `rg chakra\|mui\|antd\|tailwind web/` → none. After the change: web src LOC 1477 <= 3000. | **Holds.** CSS grid, no new dep. |

```
$ uv run python scripts/check_budgets.py   # origin/main before the change

BUDGETS
  ok    api src LOC               4000 <= 4000
  ok    web src LOC               1315 <= 3000
  ok    api routes                   1 <= 10
  ok    agent tools                  4 <= 6
  ok    graph nodes                  0 <= 8
```

```
$ rg "setResult" web/src/App.tsx
  const [result, setResult] = useState<AskResponse | null>(null);
    setResult(null);          # the transition that must change
      setResult(response);
```

No `thread_id`, `localStorage`, or `sessionStorage` under `web/src`.
