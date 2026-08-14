# What a user can now do that they could not before

<!-- One sentence, in user terms. If you cannot write it, this is not a PR. -->

## Evidence

<!-- Paste real output. "Tests pass" is not evidence. -->

```
$ make eval
```

```
$ make demo --repeat 3
```

## Checklist

- [ ] The sentence above is about a **user**, not about the codebase.
- [ ] `make check` passes and **no budget was raised**.
      (If a budget needed raising, that is a separate PR of your own.)
- [ ] Retrieval and answered rates did not regress on the `long_tail` tier.
- [ ] p95 latency did not regress.
- [ ] Every new response path still renders the API URL, MOE, GEOID and universe.
- [ ] No new blocking clarification prompt.
- [ ] `docs/ARCHITECTURE.md` updated if the shape of the system changed.

## Files touched

<!-- CI comments the count. Over ~15 is a redesign wearing a feature's clothes:
     say why here, or split it. -->
