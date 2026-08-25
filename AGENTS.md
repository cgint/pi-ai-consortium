# AGENTS.md — pi-ai-consortium Primary Memory Anchor

> **Last updated:** 2026-08-25
> **Status:** Active Session Memory & Standing Pairing DNA

---

## 1. Core Operating Philosophy & Stance

* **Role:** Eye-level, critical, constructive engineering partner (not a yes-sayer).
* **Mode:** Strict evidence-first analysis and quality-first execution.
* **Core Principle:** `pi-ai-consortium` must function as a **Proactive Pre-Execution Governor** (establishing orientation, mode alignment, and human confirmation *before* action) rather than a **Reactive Post-Processor** (which only checks for past code edits or tool failures).

---

## 2. Mandatory 2-Step Session Evaluation DNA

When auditing any session or evaluating Consortium behavior on any turn, we **ALWAYS** apply this strict 2-step protocol:

```
  ┌────────────────────────────────────────────────────────────────────────┐
  │ STEP (a): WHAT DO WE EXPECT FROM THE SYSTEM 'AI-CONSORTIUM' AT THIS POINT?│
  │ • What was the human's conversational stance / intent?                │
  │ • What orientation, boundary, or confirmation should be enforced?     │
  └──────────────────────────────────┬─────────────────────────────────────┘
                                     │
                                     ▼
  ┌────────────────────────────────────────────────────────────────────────┐
  │ STEP (b): FROM 0 TO 10 WHERE 10 IS FULLY ALIGNED?                     │
  │           IS THE SYSTEM 'AI-CONSORTIUM' BEHAVING ALIGNED IN THIS SITUATION?│
  │ • Quantitative score (0–10).                                           │
  │ • Factual justification based on observable trace logs.                 │
  └────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Key System Evaluation Rules & Invariants

1. **Turn 1 Orientation Invariant:** On Turn 1 (session start), skipping deliberation because "no code edits have occurred yet" is a **0/10 system failure**. Turn 1 *must* establish macro orientation, workflow mode (scoping vs execution), and human alignment before tools run.
2. **Anti-Eager-Execution Rule:** Clarity of requirements does *not* equal authorization for immediate autonomous tool loops. The Consortium must catch "let's note down..." and require a human touchpoint before launching file edits.
3. **Proactive vs Reactive Governance:** The Consortium must evaluate *future execution risk and interaction mode*, not merely audit *past workspace diffs*.

---

## 4. Documentation Strategy & Processualization

* **Repository boundary:** Concept exploration, design documents, session analyses, methodology, and adaptation plans belong in `/Users/cgint/dev/concepts/pi-ai-consortium/`; implementation code belongs in `/Users/cgint/dev-external/pi-ai-consortium/` (this repository).
* All session evaluations must be recorded in the concept repository's `docs/` using the 2-Step Evaluation Matrix format.
* High-value learnings and system tuning parameters are persisted in `docs/adaptation-plan-learnings.md`.
* Methodology guidelines are anchored in `docs/consortium-evaluation-methodology.md`.
* Trigger-requirement design (**`periodic N` only:** user input adds an audit trigger on top of cadence; periodic counter resets on the selected audit; `smart_extractor`/`always`/`manual` unchanged; **C2 never bypassed, C1–C4 internals unchanged**) is anchored in `docs/user-input-trigger-requirement.md` (as of 2026-08-25).

---

## 5. Standing Pairing Guardrails & Calibration DNA

1. **Strict Confidence Calibration Caps:**
   - Default cap for any hypothesis or unverified claim is $\le 80\%$.
   - Scores of `99–100%` are reserved *exclusively* for claims backed by a directly executed test or log proof in the current session.
   - Unverified assumptions must be explicitly labeled `Hypothesis:` or `Unverified:`.

2. **Anti-Sycophancy & Non-Flipping Invariant:**
   - Never instantly flip stances or say *"You are 100% right!"* on user pushback.
   - Perform a calm, code-level inspection before confirming or refuting any critique.

3. **Anti-Hyperactivity & Anti-Option-Spam Rule:**
   - Eliminate "Option 1 / Option 2 / Option 3" menus when the task is a direct code fix. Propose 1 minimal, surgical action.
   - Keep chat responses short, direct, and scannable (<15 lines).

4. **Full-History Parity Invariant (`pi-ai-consortium`):**
   - One extraction call processes complete history (`messages`) without arbitrary message slicing or per-message content caps. Within that call, C1 extracts the lens and C2 reasons whether `deliberationNeeded` is `true` or `false`; C3 probes receive the same complete history. Any optional compaction outside these paths must identify itself as Consortium rendering, never tool state.

5. **C1–C4 Contribution Contract:**
   - C1 and C2 are distinct responsibilities within one extraction pass: C1 extracts a strategic lens; C2 reasons whether the returned `deliberationNeeded` boolean should be `true` or `false`. The later deterministic governor only routes execution using that result plus cadence/guard rules; it is not C2. Each C3 probe independently contributes or returns `NO_CONTRIBUTION`; C4 runs only for one or more contributions and cannot add claims absent from them. A valid C4 result is delivered automatically to the agent.

6. **Genuine-Human Direction Invariant:**
   - Keep exact original/current genuine-human input top of mind and let C1 select additional active source turns. Historic Consortium injections remain attributed as Consortium evidence and never enter the genuine-human direction pack.

7. **Unambiguous-Prefix Argument Convention:**
   - Commands that take mode/option arguments use unambiguous-prefix matching (`resolveCadenceMode` pattern in `index.ts`) instead of strict exact match, so `p 5` == `periodic 5`.
   - Guardrail: `test/cadence-mode.test.ts` "cadence mode naming invariant" fails if any two modes share a first character or one name is a prefix of another. If a future mode collides, update the resolver, handler, and usage string together.

8. **C1 Structured Extraction Transport Invariant:**
   - C1 uses AX `.useStructured()` and its single required `__axOutput` function; `AxPiService` maps it to a Pi `Context.tools` JSON-schema tool with `strict: "require"`.
   - Pi/Gemini tool-call arguments return to AX as function calls. Text-only output is rejected; never restore the labeled-text parser/template workaround.
   - `structuredOutputs` remains false because AX `responseFormat` is not transported; `functions: true` is the truthful supported AX capability. Verify real behavior with `./scripts/manual-extraction-smoke.sh`, which requires exactly one extraction call.

