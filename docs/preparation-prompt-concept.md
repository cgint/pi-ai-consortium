# Preparation Prompt — Concept & Requirements

**As-of:** 2026-07-22 (updated after critical analysis + advisor review)
**Status:** Discovery / design discussion (pre-implementation)
**Purpose:** Collect observations, constraints, requirements, and design ideas for a preparation step that runs *before* the probe fan-out in the consortium deliberation pipeline.

---

## Motivation

The consortium's current `buildUserContextFromMessages()` feeds the full raw conversation history to every probe. This causes systemic failures:

| Observed failure | Root cause |
|---|---|
| Probe fires BLOCK **before agent has read the file** (premature judgment) | Probes evaluate on user prompt alone; no phase awareness |
| Probe warns agent to "stop reading source code" when agent is reading a JSONL session log that *contains* source code paths (layer confusion) | No semantic distinction between current actions and embedded historical content |
| Probes react to session constraints that **no longer apply** (stale state) | Session flags captured at startup, never refreshed |
| Responder flags incomplete prior task even after user explicitly pivots (stale goal) | No recency/supersession awareness |

See `probe-behavior-issues.md` for detailed analysis of all three documented failure patterns.

---

## Core constraint: factual augmentation, not replacement

The preparation step **adds** a clarifying structured view on top of the raw history. It does **not** replace or compress the full raw history that probes receive.

```
event.messages
     │
     ├── raw history (unchanged, as today) ──────────┐
     │                                                │
     └── [Preparation step] ──→ compact view ─────────┤
                                                      │
                                                      ▼
                                             userContext fed to probes:

  [RAW HISTORY]
  (unchanged, full conversation dump)

  [CURRENT SITUATION]    ← new section, prepended or appended
  ...
```

Rationale: removing/compressing the full raw history is a separate challenge and should not be coupled to this step.

---

## Key requirement: the "latest user message" is NOT always the active goal

**This is critical.** The user's active goal may be the 5th-to-last user message, with subsequent messages being clarifications, steering, or side-context — not superseding the original goal.

Therefore the preparation step must **not** take the simplistic approach of "latest user message = current goal." Instead it should examine the user messages specifically (roughly the last 10 user messages) plus surrounding context (last ~50 messages total to stay within the last 10 user messages range) to determine:

- What is the actual current goal/objective?
- Has a prior goal been explicitly superseded?
- Which user messages are clarifications/steering vs. goal changes?

**The preparation step must be factual and neutral:**
- Must not lean toward any solution direction
- Must not be overconfident about inferred goals
- Must surface ambiguities and uncertainties, not paper over them
- Must output verifiable observations about the conversation state
- When uncertain about the goal, it must say so explicitly rather than guess

**Input window:** The "~last 10 user messages / ~50 total messages" heuristic should be a configurable parameter, not a hardcoded constant, so it can be tuned per session type.

---

## Implementation approach: hybrid (start deterministic, target LLM)

### Phase 1: Deterministic extractor (MVP)

Start with a deterministic extractor that:
- Pulls the last N user messages verbatim
- Strips tool output from surrounding context
- Formats as a lightweight `[RECENT USER DIALOGUE]` section

**Advantages:** Zero additional LLM cost, zero hallucination risk, establishes the pipeline and output format. Proves the concept before investing in LLM extraction.

**Limitations:** Cannot semantically resolve "which message is the actual goal?" when the answer requires understanding intent. Likely insufficient for the harder failure modes.

### Phase 2: LLM-based extraction (optional)

Add an LLM-based preparation call behind an opt-in flag (`CONSORTIUM_PREP_LLM=true`). The LLM call:
- Receives the same full context as the probes (for KV-cache alignment)
- Outputs the structured `[CURRENT SITUATION]` section
- Is serialized before probes for cache reuse on compatible engines

**Advantages:** Can understand semantics, resolve goal ambiguity, detect supersession chains.

**Costs:** Adds one LLM call to the serial pipeline (currently 5 probes + synthesis = 6 calls → 7 calls). Latency impact depends on the model used — a smaller/cheaper model for the prep step may mitigate this.

### Decision gate for Phase 1 → Phase 2

Move from deterministic to LLM when:
1. Deterministic extraction demonstrably fails to resolve >50% of "stale goal" false positives in testing with real session logs
2. The user accepts the latency trade-off for improved probe accuracy

Stay with deterministic if:
1. Fixed-window output resolves the concrete false positives (responder stale goal, navigator layer confusion) acceptably
2. LLM latency would make the consortium unusable on the target hardware

---

## KV-cache: nice-to-have, not architecture driver

**Do not let KV-cache optimization drive the architecture.**

The preparation step and probes share the same input prefix, which *could* enable prefix cache reuse across sequential calls on compatible inference engines when run in serial mode. However:

- **Different system prompts break prefix caching on most engines.** The prep step has its own system prompt, different from the probe system prompts. On most engines, this means no cache reuse across the prep → probe boundary regardless of shared user context.
- This was explicitly warned about in `CONSORTIUM_INTEGRATION_REVIEW.md`: "Different system prompts change the request prefix before the shared history, which commonly prevents prefix-cache reuse across probes."
- If an engine does support prefix reuse despite different system prompts, serial execution may benefit — but this is a **bonus**, not a requirement.

Design the preparation step to be robust **even if cache reuse fails entirely.**

---

## What the preparation step should output

A compact, factual structured section. Fields should evolve through iteration, not be locked upfront.

Initial shape (illustrative, not frozen):

```
[CURRENT SITUATION]
Goal origin: user message #N ("pls make sure it is deployed fresh")
Current objective: add comment to build.sh explaining why latest tag is used intentionally
Recent corrections: user clarified that "deploy fresh" concern is handled by deploy.sh pulling specific latest tags
Active phase: annotation/clarification (not deployment)
Open ambiguities: none

[SESSION STATE]
Read-only mode: false (disabled by user at message #M)
Current model: ...
```

**Crucial rule:** When the preparation step cannot determine a clear goal (conflicting user messages, insufficient context), it **must output the ambiguity explicitly** rather than guessing. Example:

```
[CURRENT SITUATION]
Goal: UNCLEAR — user mentioned X at message #3 but said Y at message #7 without explicit supersession
Active phase: unclear
Open ambiguities: relationship between message #3 ("deploy fresh") and message #7 ("add comment first") not resolved
```

This prevents the prep step from becoming a single point of failure for hallucinated context that all probes anchor on.

---

## Risk analysis

### Amplification of wrong context

If the preparation step confidently outputs a wrong "current goal," all subsequent probes may anchor on it, making failures **worse** than today. Mitigation:

- The "factual and neutral" instruction is a prompt-level mitigation, not a guarantee
- Phase 1 (deterministic) avoids this risk entirely
- Phase 2 (LLM) must output uncertainty explicitly when confidence is low
- Probes should treat the prep output as advisory context, not authoritative — they still have the raw history to cross-check

### Latency multiplication

Current pipeline: 6 LLM calls serial (5 probes + synthesis) → potentially 7 with prep step. On local models with 2-5s per call, the user waits 35+ seconds before the agent gets context. Mitigation:

- Phase 1 adds zero additional LLM latency
- Phase 2 could use a much smaller/cheaper model for the prep call (e.g. 3B-8B parameter) to keep per-call cost low
- If latency is unacceptable, the prep step could be skipped entirely (opt-in flag)

### Scope creep

The preparation step could grow into a mini-supervisor if not bounded. **Keep scope strictly to context summarization, not decision-making.** The prep step observes and clarifies; it does not evaluate, warn, or recommend actions.

---

## Relationship to other concepts

This is distinct from but related to:

- **pi-prompt-atomic-factualise** — entity extraction and pronoun resolution for user prompts. That concept resolves ambiguous references *before* the prompt reaches the agent. The preparation step is about giving probes better situational context *before* they deliberate.
- **supervisor SessionState schema** — defines a compact session projection (goal, objective, phase, recent direction, records with supersession). The preparation step may eventually use a subset of this schema for its output format.
- **inspector / Stream 2a** — creates durable semantic projections from session history with claim categories, epistemic types, evidence refs. The preparation step is lighter-weight and live (per-turn), not a durable evaluation.

---

## Open questions

- What is the minimum viable output for the preparation step? (prove value before adding more fields)
- Should the prep step use a smaller/cheaper model than the probes if it's LLM-based?
- Should synthesis also receive the preparation output, or only the probes?
- What happens when the preparation step disagrees with a probe's reading of the same history? (working hypothesis: probe should win — prep is context, not authority — but this needs testing)
- How does this interact with repeated deliberation during tool loops? (avoid re-running prep on every turn when context hasn't changed meaningfully)
- What is the acceptable latency budget for the prep step? (needs user input)
