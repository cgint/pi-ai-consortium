# User-Input Trigger for Consortium Deliberation

**As-of:** 2026-08-25
**Status:** Requirement captured — NOT yet implemented. No code changed.
**Owner intent:** human (cgint) — recorded from a Strict-Discuss read-only session.

---

## 1. Requirement (what the user wants)

Deliberation should fire **after user input**, as a *first-class* "initial
deliberation" point — not "randomly 3–10 steps later" depending on the
cadence strategy.

Key framing (user's own words, condensed):

- "This 'on every user input' is an **ADDITIONAL** criterion."
  User input is a *second* trigger that sits **on top of** the existing
  cadence, not a replacement for it.
- User input can only make deliberation fire **sooner**, never later.
- The periodic backstop must still work on its own for long autonomous
  stretches where the user is not typing.

Worked example the user gave (cadence `periodic 10`):

```
agent takes 5 actions  → counter = 5
user types input       → FIRE now (even though 5 < 10)
                        counter resets to 0
10 more LLM calls      → FIRE again on the periodic clock, no user input needed
                        counter resets to 0
```

So the desired trigger is a **union**:

```
run = (new user input since last run)   ← NEW
    OR (turnsSinceLastAudit ≥ cadence)  ← existing backstop
```

## 2. Agreed design decisions

| # | Decision | Status |
|---|----------|--------|
| A | After a user-input-triggered run, the periodic counter **resets to 0**. | **Agreed** (user, 2026-08-25) |
| B | In `manual` mode, user input does **NOT** trigger the consortium. | **Agreed** (user: "only 'manual' does not trigger") |
| C | In `smart_extractor`, `always`, `periodic N`, user input **does** trigger. | **Agreed** |
| D | **C2 is never bypassed.** The trigger change touches only *when* the pipeline runs; C1–C4 internals (extraction, probes, synthesis, prompts, gating) are unchanged. | **Agreed** (user, 2026-08-25: "C2 is never bypassed — inside C1-C4 nothing changes — it is only about triggering the whole thing in the first place") |

### Per-mode semantics on user input

| Mode | On user input | On periodic hit |
|------|---------------|-----------------|
| `smart_extractor` | Evaluate C2 on the fresh input; probes run only if C2 says `deliberationNeeded: true` | Force full audit (existing `maxTurnGap`-style behavior) |
| `always` | Full audit | (already fires every LLM call) |
| `periodic N` | **Full audit** now | Full audit on Nth LLM call |
| `manual` | **Nothing** | **Nothing** |

> Note: in `smart_extractor`, "trigger on user input" means the
> evaluation pipeline runs at the right moment; C2 still owns whether the
> 5-probe audit actually executes — C2 is **never bypassed** (Decision D).
> This preserves the ~85% token savings that mode exists for.

## 3. What is current behavior today (evidence)

Established by reading the code in this session (no changes made):

- **Trigger is the `context` event**, which fires **before every LLM
  call**, including each tool-loop iteration inside one user turn — *not*
  once per user input.
  - `index.ts` — `pi.on("context", ...)` is where `runDeliberation` is
    called; `turnState.deliberation` guards concurrent runs.
  - `pi` event model — `TurnStartEvent` = "Fired for each turn (one LLM
    response + tool calls)"; `ContextEvent` = "Fired before each LLM
    call." `ContextEvent` carries only `messages` (no `turnIndex`).
  - `TurnStartEvent`/`TurnEndEvent` carry `turnIndex` but **no** messages.
  - `InputEvent` fires once per user submission and carries `text` (not
    the full history).
- **`input` event only logs** — it does not currently trigger
  deliberation.
- **`turn_start` resets `turnState.deliberation` on each LLM call**, which
  is why the full deliberation attempt re-runs on every LLM call in a tool
  loop.
- **`turnsSinceLastAudit` counts LLM calls**, not user turns.
  - `smart_extractor`: extraction (C1/C2) runs on every LLM call; the
    5-probe audit runs when C2 says `deliberationNeeded: true` or
    `turnsSinceLastAudit ≥ maxTurnGap (20)`.
  - `periodic N`: nothing runs until the counter reaches N, then full
    audit, then reset.

### The defect this fixes

Because the trigger is per-LLM-call, in `periodic N` the audit fires on the
Nth **LLM call** (unrelated to user input), and in `smart_extractor` C2's
"yes" can land a few calls into a long tool loop. Both produce the observed
"randomly 3–10 steps later" timing.

## 4. Key insight (shared understanding)

The "high value vs low value" judgment (new direction / constraint /
correction vs continuation / lookup) is **not a new gate to build** — it is
already exactly what C2 (`deliberationNeeded`) computes on the full
history. This change therefore touches **only the trigger point** (when the
pipeline runs), not the decision logic (whether probes run).

## 5. Proposed minimal mechanism (design only — not approved)

The constraint: `context` is the only hook that carries `event.messages`
(the full history the probes/extraction need). So we do not move the
trigger to `input`; instead we **gate the `context` handler** on "this is
the first LLM call since the last user input, OR the periodic backstop is
due."

```js
let pendingUserTurn = false;   // set on user input, consumed on first context
pi.on("input", async (event, ctx) => {
  // ...existing logging...
  pendingUserTurn = true;
  return { action: "continue" };
});

pi.on("context", async (event, ctx) => {
  if (!enabled) return;
  if (turnState.deliberation) return;          // existing re-entrancy guard
  // NEW gate: fire only on a fresh user turn OR a due periodic backstop.
  const periodicDue = /* per-mode counter check */;
  if (!pendingUserTurn && !periodicDue) return;
  if (event.messages.length === 0) return;
  pendingUserTurn = false;                     // consume the flag
  // ...runDeliberation(event.messages, ...) as today...
});
```

- The existing `turn_start` reset becomes inert for gating (harmless to
  keep, or remove).
- The governor + cadence logic (`src/governor.ts`) stays intact.
- **Nothing inside C1–C4 changes** (Decision D) — no prompt edits, no
  extraction/probe/synthesis edits. Only the outer trigger gate.

## 6. Open questions (need human call before implementation)

### Resolved in discussion

- **D1 (was open) — `smart_extractor` on user input: C2-gated, not forced.**
  C2 is never bypassed (Decision D).
- **D2 (was open) — Counter unit: LLM calls.** Matches the user's "10
  actions later"; resets on any fired audit (Decision A).
- **D4 (was open) — `manual` + user input:** no trigger (Decision B).

### Still open

- **D3 — Resume / new-session orientation.** On `/resume` or a new session
  there is no `input` event before the first LLM call, so the first trigger
  would be the user's first typed message. Do we want an orientation pass on
  resume? Could set `pendingUserTurn = true` on
  `session_start { reason: "resume" | "new" }`. (AGENTS.md *Turn 1
  Orientation Invariant* argues for it.)

## 7. Verification plan (TDD, when implementation is approved)

Write the red tests first:

1. `periodic 10`, counter at 5, a user input arrives → audit fires now,
   counter resets to 0.
2. After a user-input-triggered fire, the next 10 LLM calls with no user
   input → periodic fires at 10, counter resets.
3. `manual` mode: user input → no fire.
4. `smart_extractor`: user input → C2 evaluation runs on the first LLM call
   of that turn; probe run follows C2 (per Decision D: C2-gated, never forced).
5. Tool-loop LLM calls after the first (no new user input, periodic not
   due) → no fire (no re-entrant deliberation mid-loop).

Run: `npx tsc --noEmit`, `npx vitest run`, `./precommit.sh`.

## 8. Out of scope (for now)

- Changing C2's prompt or the probe/synthesis prompts.
- Mid-turn re-evaluation (that is `pi-self-reflect`'s role).
- The full-history budget / compaction strategy (separate, documented in
  `docs/2026-08-24-consortium-session-behavior-investigation.md`).
