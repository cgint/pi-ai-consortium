# IMPLEMENTATION REPORT — headline block

Put this block at the **VERY TOP of the output file**. Hard cap ~12 lines.

```text
- Change ID:      <nn-topic>
- Output:         <absolute report path>
- Status:         complete | partial | premise-wrong | scope-blocked | verification-failed
- HEADLINE:       <single observable result, with changed file:line>
- BEHAVIOR:       unchanged | authorized change: <exact change>
- FILES CHANGED:  <paths, or NONE>
- VERIFIED:       <commands + pass/fail; never just "tests pass">
- CONTRADICTS:    <brief premise falsified, or NONE>
- NOT FOUND:      <load-bearing absences only>
- UNDETERMINED:   <runtime-only or unresolved checks, and why>
- RESIDUAL RISK:  <highest remaining risk, or NONE>
```

## Rules

- `HEADLINE` states what now works, not that work completed.
- `BEHAVIOR` must name any runtime change. If it exceeds the authorization
  boundary, status is `scope-blocked`, not complete.
- `VERIFIED` lists actual commands and outcomes. A path or green status alone is
  not verification.
- `CONTRADICTS` remains load-bearing: implementation often exposes a false design
  premise. Never bury it.
- Do not claim runtime/provider behavior from unit tests. Put that under
  `UNDETERMINED` until exercised against the pinned runtime.
- The main session will inspect the diff and use an independent reviewer before
  committing. Do not commit from the worker run.
