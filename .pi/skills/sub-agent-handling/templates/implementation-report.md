# IMPLEMENTATION REPORT — headline block

Put this block at the **VERY TOP of the output file**. Hard cap ~12 lines.

```text
- Change ID:      <nn-topic>
- Output:         <absolute report path>
- Status:         complete | partial | premise-wrong | scope-blocked | verification-failed
- HEADLINE:       <single observable result, with changed file:line>
- BEHAVIOR:       unchanged | authorized change: <exact change>
- FILES CHANGED:  <paths, or NONE>
- REQUIREMENTS:   <N/N satisfied; list any failed requirement numbers>
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
- `REQUIREMENTS` must map every numbered brief requirement to `PASS`, `FAIL`, or
  `UNDETERMINED` in the detailed report. **Status `complete` is forbidden unless
  every requirement is PASS.**
- `VERIFIED` lists actual commands and outcomes. A path or green status alone is
  not verification. Passing unit tests does not prove production wiring unless
  at least one test traverses that production path.
- `CONTRADICTS` remains load-bearing: implementation often exposes a false design
  premise. Never bury it.
- If `RESIDUAL RISK`, `UNDETERMINED`, or the prose says a required behavior is
  deferred to a later stage, status cannot be `complete`; use `partial` or
  `scope-blocked`. A report may not call an unmet requirement "by design" to
  redefine the brief.
- Do not claim runtime/provider behavior from unit tests. Put that under
  `UNDETERMINED` until exercised against the pinned runtime.
- Do not label a test integration/production-path evidence when it copies the
  production logic into a helper. It must call the actual production entrypoint
  or fire the real registered handler. For branch coverage, report how the test
  proves the branch precondition was reached, not only the test name.
- The main session will inspect the diff and use an independent reviewer before
  committing. Do not commit from the worker run.
