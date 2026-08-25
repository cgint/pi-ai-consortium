# Periodic User-Input Trigger — Requirement and Plan

**As-of:** 2026-08-25
**Status:** Implemented; code-clarity refactor in progress.
**Scope:** One behavioral change only.

## Requirement

In **`periodic N` mode only**, a genuine user input starts the periodic audit
immediately and resets the periodic counter to `0`.

```text
periodic 10, counter = 5
user input → audit now; counter = 0
10 later LLM calls without user input → periodic audit again; counter = 0
```

This is additive to the periodic cadence:

```text
periodic audit = user input OR Nth LLM call
```

No other mode gains a user-input trigger.

## Behavioral boundary

| Mode | Required behavior |
|---|---|
| `periodic N` | **Changed:** user input starts an audit immediately; N-call cadence remains the backstop. |
| `smart_extractor` | **Unchanged:** enters C1/C2 on every LLM call; C2 gates C3. |
| `always` | **Unchanged:** runs the probe audit on every LLM call. |
| `manual` | **Unchanged:** never auto-runs. |

## Terminology requirement

These terms describe distinct actions and must be reflected in readable code:

- **Deliberation pass:** run C1/C2 extraction. C2 decides whether a probe
  audit is warranted.
- **Probe audit:** run C3 probes, then run C4 only when C3 has one or more
  contributions.
- **Forced probe audit:** policy enters C3 regardless of C2's outcome. It
  does not guarantee C4, because C4 still requires C3 contributions.

`always` always runs a **probe audit**. `smart_extractor` always runs a
**deliberation pass**, but conditionally runs a **probe audit**.

## Invariants

- C1–C4 internals, prompts, extraction, probe behavior, and synthesis are
  unchanged.
- C2 is never removed or modified. Periodic policy may force the existing
  periodic audit exactly as its cadence already does.
- `smart_extractor`, `always`, and `manual` retain their pre-change control
  flow.
- The periodic counter counts LLM calls and resets when a periodic audit is
  selected.
- No resume/new-session orientation behavior is included.

## Implementation shape

`index.ts` owns the single new outer trigger:

```ts
if (governorMode === "periodic") {
  const periodicSchedule = schedulePeriodicAudit({
    turnsSinceLastAudit,
    pendingPeriodicUserInput,
    periodicInterval,
  });
  // Audit when user input is pending or the Nth LLM call is due.
}
```

`pendingPeriodicUserInput` is set only when an input arrives while the mode is
`periodic`. `schedulePeriodicAudit` uses an effective interval count solely to
enter the unchanged periodic governor; it does not alter C1–C4.

## Verification

- `test/deliberation-schedule.test.ts`: immediate periodic input audit,
  counter reset, exact N-call cadence.
- `test/disabled.test.ts`: `smart_extractor` retains its per-context path
  without new input.
- Full verification: `./precommit.sh`.

## Out of scope

- Any behavior change to `smart_extractor`, `always`, or `manual`.
- C1–C4 or prompt changes.
- Mid-turn reflection, resume orientation, and history-compaction changes.
